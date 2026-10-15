"""agent 臂（agent 级数据计划第三阶段，2026-10-15）：一个**受限的选题执行循环**，不是另一版提示词。

模型的权限只有三样：查阅允许的历史证据、调整自由位排序、提交结果。两个真正执行的工具：

    retrieve_history   读这个孩子**允许范围内**的真实 session 记录（身份和截止时间由决策上下文注入，模型改不了），
                       返回评分、实际展示过的反馈 / 陪伴、完成与修改状态、来源编号。不存在的就标 missing，不补推断。
    validate_offer     对一份拟提交的自由位排序做**确定性**校验：成员资格、重复、数量、固定位不动、任务版本、
                       引用的记录是否存在且属于允许的历史。返回具体错误码和位置，让模型有机会改。
                       引用存在 ≠ 理由正确；排序合法 ≠ 最适合这个孩子——这里不装评委。

工具的返回来自真实记录或程序检查，模型不能自己写「已检索」「已验证」。每次工具执行在 calls.jsonl 里
一条 local 记录（tool_name / requested_by=model|runtime / step / 参数 / 返回），整次选题共用一个 group。
循环（run_agent）有结束条件和预算：模型请求次数、检索次数、校验次数、总时限；最终提交永远由后端
再做一次共同的硬校验（requested_by=runtime），通过才采用，否则交回修正或回退 rules。
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from . import history as history_mod
from . import llm
from .quests import QUESTS_BY_ID
from .scoring.base import DIM_KEYS
from .storage import session_events, session_feedback, sid_of
from . import events as ev

PROMPT_VERSION = "agent/v1"
TEXT_CAP = 240
MAX_SESSIONS_PER_RETRIEVE = 2

# 第一版预算（用户 2026-10-15 定的起始值，按实测调）
BUDGET = {
    "model_attempts": 4,      # 每次 decision 最多几次 HTTP 尝试（含重试）
    "retrieve": 2,            # 主动检索最多几次
    "validate": 2,            # 主动校验最多几次（最终的后端校验另计，不调模型）
    "seconds": 150.0,         # 整次 decision 的总期限（不是单次 90 秒逐轮累加）
}

ERRORS = ("BAD_ARGUMENT", "UNKNOWN_TASK", "NOT_IN_POOL", "NOT_ON_MAP", "FIXED_SLOT_TASK", "DUPLICATE_TASK",
          "WRONG_COUNT", "INVALID_EVIDENCE_REF")


class AgentContext:
    """一次 decision 的执行上下文：身份、截止时间、冻结候选、自由位，全部由后端注入，模型只能在里面动。"""

    def __init__(self, *, store, decision: Dict[str, Any], who: Dict[str, Any], before: str,
                 account_scope: Optional[Dict[str, Any]] = None, pool: List[str], n_free: int, fixed: List[str]):
        self.store = store
        self.decision = decision
        self.who = dict(who or {})
        self.before = before
        self.scope = account_scope or {"account_id": self.who.get("account_id", ""), "device_windows": {}}
        self.pool = list(pool)
        self.n_free = int(n_free)
        self.fixed = list(fixed)
        self._allowed: Optional[List[Dict[str, Any]]] = None
        self.evidence_seen: Set[str] = set()       # retrieve_history 返回过的 session id：引用只能指向这些 + representation 里的
        self.rep_sessions: Set[str] = set()

    def allowed_sessions(self) -> List[Dict[str, Any]]:
        """允许读的历史 = representation 用的那一份：同一条归属规则，截止到 before。只算一次。"""
        if self._allowed is None:
            self._allowed = history_mod.sessions_for(
                self.who.get("participant_id", ""), self.who.get("anon_id", ""),
                account_id=self.scope.get("account_id", ""), windows=self.scope.get("device_windows") or {},
                before=self.before)
        return self._allowed


def _cap(text: Any) -> Optional[str]:
    if text is None:
        return None
    t = str(text)
    return t if len(t) <= TEXT_CAP else t[:TEXT_CAP] + "…"


def _dims(record: Optional[Dict[str, Any]], dimension: Optional[str]) -> Optional[Dict[str, Any]]:
    if not record:
        return None
    dims = ((record.get("scores") or {}).get("dims") or {})
    out = {k: (v or {}).get("score") for k, v in dims.items() if k in DIM_KEYS}
    if dimension:
        out = {k: v for k, v in out.items() if k == dimension}
    return out


def _primary_dims(meta: Dict[str, Any]) -> List[str]:
    task = meta.get("task") or {}
    rub = task.get("rubric") or (QUESTS_BY_ID.get(meta.get("quest_id", "")) or {}).get("rubric") or {}
    return list(rub.get("primary_dimensions") or [])


def _family_of(meta: Dict[str, Any]) -> str:
    task = meta.get("task") or {}
    return task.get("family") or (QUESTS_BY_ID.get(meta.get("quest_id", "")) or {}).get("family") or (meta.get("quest_id") or "").split("_")[0]


def retrieve_history(ctx: AgentContext, *, family: Optional[str] = None, dimension: Optional[str] = None,
                     feedback_type: Optional[str] = None, limit: int = 2) -> Dict[str, Any]:
    """查原始记录（representation 里没展开的细节），最近的在前。返回的内容和来源版本会被记进 calls.jsonl。"""
    errors = []
    if dimension and dimension not in DIM_KEYS:
        errors.append({"code": "BAD_ARGUMENT", "detail": f"unknown dimension {dimension!r}"})
    if feedback_type and feedback_type not in ("formative", "comparison"):
        errors.append({"code": "BAD_ARGUMENT", "detail": f"unknown feedback_type {feedback_type!r}"})
    if errors:
        return {"ok": False, "errors": errors, "sessions": [], "n_matched": 0}
    try:
        limit = max(1, min(MAX_SESSIONS_PER_RETRIEVE, int(limit)))
    except (TypeError, ValueError):
        limit = 1
    rows = []
    for meta in reversed(ctx.allowed_sessions()):            # sessions_for 给的是最老在前
        if family and _family_of(meta) != family:
            continue
        if dimension and dimension not in _primary_dims(meta):
            continue
        d = ctx.store.dir(sid_of(meta))
        fbs = [f for f in session_feedback(d) if f.get("source", "ai") == "ai"]
        if feedback_type and not any(f.get("feedback_type") == feedback_type for f in fbs):
            continue
        rows.append((meta, d, fbs))
    out_rows = []
    for meta, d, fbs in rows[:limit]:
        sid = sid_of(meta)
        shown_clicks = {}
        try:
            for e in session_events(d):
                if ev.canonical(e.get("type", "")) == ev.ASSIST_SHOW:
                    p = e.get("payload") or {}
                    if p.get("click_id"):
                        shown_clicks[p["click_id"]] = True
        except Exception:
            pass
        assists = []
        for c in meta.get("assist_clicks") or []:
            if c.get("text"):
                assists.append({"click_id": c.get("click_id"), "nth": c.get("nth"), "text": _cap(c.get("text")),
                                "call_id": c.get("call_id"),
                                # 没有 ASSIST_SHOW 事件就不能说孩子看过这句：如实标 unknown
                                "shown": True if shown_clicks.get(c.get("click_id")) else None})
        missing = []
        if not meta.get("before"):
            missing.append("before_scores")
        if not meta.get("after"):
            missing.append("after_scores")
        if not fbs:
            missing.append("feedback")
        if not assists:
            missing.append("assist")
        out_rows.append({
            "session_id": sid, "task_id": meta.get("quest_id"), "family": _family_of(meta),
            "task_version": (meta.get("task") or {}).get("version") or (QUESTS_BY_ID.get(meta.get("quest_id", "")) or {}).get("version"),
            "primary_dimensions": _primary_dims(meta), "at": meta.get("created_at"), "status": meta.get("status"),
            "revised": meta.get("revised"),
            "before_scores": _dims(meta.get("before"), dimension), "after_scores": _dims(meta.get("after"), dimension),
            "scores_backend": ((meta.get("before") or {}).get("scores") or {}).get("backend"),
            "feedback": [{"feedback_id": f.get("feedback_id"), "phase": f.get("phase"), "feedback_type": f.get("feedback_type"),
                          "text": _cap(f.get("text")), "backend": f.get("backend"), "call_id": f.get("call_id")}
                         for f in fbs],
            "assist": assists, "missing": missing,
        })
        ctx.evidence_seen.add(sid)
    return {"ok": True, "query": {"family": family, "dimension": dimension, "feedback_type": feedback_type, "limit": limit},
            "sessions": out_rows, "n_matched": len(rows), "truncated": len(rows) > limit,
            "source": {"before": ctx.before, "n_allowed": len(ctx.allowed_sessions())}}


def validate_offer(ctx: AgentContext, ranked: Any, evidence: Any = None) -> Dict[str, Any]:
    """确定性校验。只说合法不合法，不说好不好。"""
    errors: List[Dict[str, Any]] = []
    if not isinstance(ranked, list) or not all(isinstance(t, str) for t in ranked):
        return {"ok": False, "errors": [{"code": "BAD_ARGUMENT", "position": None, "detail": "ranked must be a list of task ids"}]}
    if evidence is not None and (not isinstance(evidence, list) or not all(isinstance(t, str) for t in evidence)):
        return {"ok": False, "errors": [{"code": "BAD_ARGUMENT", "position": None, "detail": "evidence must be a list of session ids"}]}
    seen: Set[str] = set()
    for i, t in enumerate(ranked):
        q = QUESTS_BY_ID.get(t)
        if q is None:
            errors.append({"code": "UNKNOWN_TASK", "position": i, "detail": t}); continue
        if t in ctx.fixed:
            errors.append({"code": "FIXED_SLOT_TASK", "position": i, "detail": f"{t} is a fixed (anchor) slot and cannot be moved"}); continue
        if t not in ctx.pool:
            errors.append({"code": "NOT_IN_POOL", "position": i, "detail": f"{t} is not in the frozen candidate pool"}); continue
        if q.get("legacy") or "simple" not in (q.get("tiers") or []):
            errors.append({"code": "NOT_ON_MAP", "position": i, "detail": f"{t} is not a task the map can show"}); continue
        if t in seen:
            errors.append({"code": "DUPLICATE_TASK", "position": i, "detail": f"{t} appears more than once"}); continue
        seen.add(t)
    if len(seen) != ctx.n_free:
        errors.append({"code": "WRONG_COUNT", "position": None, "detail": f"need exactly {ctx.n_free} distinct task ids, got {len(seen)}"})
    allowed_ids = {sid_of(m) for m in ctx.allowed_sessions()} | ctx.rep_sessions
    for i, ref in enumerate(evidence or []):
        if ref not in allowed_ids:
            errors.append({"code": "INVALID_EVIDENCE_REF", "position": i,
                           "detail": f"{ref} is not a session in this child's allowed history (before {ctx.before})"})
    return {"ok": not errors, "errors": errors, "n_free": ctx.n_free}


# ---- 给模型看的工具说明（两条通路共用一份，各自翻译）--------------------------------------
TOOLS: List[Dict[str, Any]] = [
    {"name": "retrieve_history",
     "description": "查看这个孩子允许范围内的真实历史记录（最近的在前，最多 2 条 session）：任务、初评/终评各维度分、"
                    "实际展示过的反馈和陪伴、是否修改过。可按任务家族（如 M6）、评分维度、反馈类型筛。身份和截止时间已固定。",
     "parameters": {"type": "object", "properties": {
         "family": {"type": "string", "description": "任务家族 id，如 M6"},
         "dimension": {"type": "string", "enum": list(DIM_KEYS), "description": "只看主考这一维的任务"},
         "feedback_type": {"type": "string", "enum": ["formative", "comparison"]},
         "limit": {"type": "integer", "minimum": 1, "maximum": MAX_SESSIONS_PER_RETRIEVE}},
         "additionalProperties": False}},
    {"name": "validate_offer",
     "description": "检查一份拟提交的自由位排序是否合法：都在候选池、不重复、数量正好、固定位不动、引用的 session 属于允许的历史。"
                    "返回具体错误码和位置。合法不等于最适合。",
     "parameters": {"type": "object", "properties": {
         "ranked": {"type": "array", "items": {"type": "string"}},
         "evidence": {"type": "array", "items": {"type": "string"}, "description": "依据的 session_id 列表"}},
         "required": ["ranked"], "additionalProperties": False}},
    {"name": "submit_offer",
     "description": "提交最终的自由位排序。后端会再做一次硬校验；不通过会把错误交回给你（预算内）。",
     "parameters": {"type": "object", "properties": {
         "ranked": {"type": "array", "items": {"type": "string"}},
         "evidence": {"type": "array", "items": {"type": "string"}},
         "why": {"type": "string", "description": "给研究员的一句话，不给孩子看"}},
         "required": ["ranked", "why"], "additionalProperties": False}},
]
