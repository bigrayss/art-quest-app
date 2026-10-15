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


# ---- 循环 -----------------------------------------------------------------------------
class AgentFailed(Exception):
    """循环没拿到合法结果。reason 直接成为 fallback_reason。"""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


SYSTEM = (
    "你是一个儿童美术练习的任务编排助手，这次要给一个孩子的地图排**自由位**。\n"
    "你拿到：孩子最近创作的摘要（representation）、冻结的候选任务（只能从这里选）、固定位（不能动）、"
    "规则臂原本会给的顺序（仅供参考）。\n"
    "你能做的只有三件事，每轮选一件：\n"
    "- retrieve_history：摘要不够用时，查这个孩子允许范围内的真实记录（评分、实际展示过的反馈和陪伴、是否修改）。身份和截止时间已固定。\n"
    "- validate_offer：提交前先检查一份排序合不合法（可选）。\n"
    "- submit_offer：提交最终排序和一句给研究员的理由。后端会再做一次硬校验，不通过会把错误交回给你。\n"
    "原则：信息够了就直接提交，不要为了显得认真而检索；引用只写你真的查到的 session_id；不要编造任务 id。\n"
    "只通过工具调用行动，不要在正文里写排序。"
)


def _initial_prompt(ctx: AgentContext, rep: Optional[Dict[str, Any]], budget: Dict[str, Any]) -> str:
    from .selection_llm import describe, digest
    d = ctx.decision
    return (
        f"需要排出 {ctx.n_free} 道（自由位数量）。固定位不动：{json.dumps(ctx.fixed, ensure_ascii=False)}。\n"
        f"规则臂原本会给：{json.dumps(d.get('rules_fill') or [], ensure_ascii=False)}。\n"
        f"预算：最多检索 {budget['retrieve']} 次、主动校验 {budget['validate']} 次；总共最多 {budget['model_attempts']} 次模型请求。\n"
        f"允许读的历史：截止 {ctx.before} 之前、共 {len(ctx.allowed_sessions())} 条 session。\n\n"
        f"孩子的过往摘要：\n{json.dumps(digest(rep), ensure_ascii=False, indent=1)}\n\n"
        f"候选任务：\n{json.dumps([describe(t) for t in ctx.pool], ensure_ascii=False, indent=1)}"
    )


def _compact(result: Any, cap: int = 4000) -> str:
    text = json.dumps(result, ensure_ascii=False)
    return text if len(text) <= cap else text[:cap] + "…"


def run_agent(ctx: AgentContext, rep: Optional[Dict[str, Any]], *, parent: Optional["llm.CallContext"],
              budget: Optional[Dict[str, Any]] = None, clock=time.monotonic) -> Dict[str, Any]:
    """受限的执行循环。返回 {"ranked", "why", "evidence", "agent": {...轨迹与计数...}}；拿不到合法结果抛 AgentFailed。

    parent 是这次选题的记录上下文（purpose=select 的 group）：每一轮模型请求是组里一个 operation（tags.step / role），
    每次工具执行一条 local 记录（tool_name / requested_by）。没有 parent 也能跑，只是不落盘。
    """
    budget = {**BUDGET, **(budget or {})}
    t0 = clock()
    messages: List[Dict[str, Any]] = [{"role": "user", "content": _initial_prompt(ctx, rep, budget)}]
    trace: List[Dict[str, Any]] = []
    counts = {"rounds": 0, "tool_calls": 0, "retrieve": 0, "validate": 0, "submit": 0, "runtime_validate": 0}
    nudged = False
    step = 0

    def attempts() -> int:
        return parent.count_remote() if parent is not None else counts["rounds"]

    def record_tool(name: str, args: Dict[str, Any], result: Dict[str, Any], requested_by: str, model_call_id: Optional[str], secs: float):
        step_no = len(trace) + 1
        rec_id = None
        if parent is not None:
            rec = parent.local(backend="runtime", input={"tool": name, "arguments": args}, output=result,
                               outcome="ok" if result.get("ok", True) else "error", seconds=secs,
                               tags={"tool_name": name, "requested_by": requested_by, "step": step_no, "model_call_id": model_call_id})
            rec_id = rec["call_id"]
        trace.append({"step": step_no, "kind": "tool", "tool_name": name, "requested_by": requested_by,
                      "call_id": rec_id, "model_call_id": model_call_id, "ok": bool(result.get("ok", True)),
                      "errors": [e.get("code") for e in (result.get("errors") or [])]})
        return rec_id

    while True:
        if clock() - t0 > budget["seconds"]:
            raise AgentFailed("timeout", f"decision deadline {budget['seconds']}s")
        if attempts() >= budget["model_attempts"]:
            raise AgentFailed("budget_exhausted", f"{attempts()} model attempts")
        counts["rounds"] += 1
        step += 1
        model_call_id = None
        with llm.operation(parent, tags={"step": len(trace) + 1, "role": "model_round", "round": counts["rounds"]}) as op:
            try:
                reply = llm.claude_tools(SYSTEM, messages, TOOLS, max_tokens=800)
            except Exception as e:
                name = type(e).__name__
                raise AgentFailed("timeout" if "Timeout" in name else ("bad_output" if "BadOutput" in name else "error"),
                                  f"{name}: {e}"[:300])
            model_call_id = op.last_call_id if op is not None else None
        trace.append({"step": len(trace) + 1, "kind": "model", "call_id": model_call_id, "round": counts["rounds"],
                      "tool_calls": [c["name"] for c in reply["tool_calls"]], "text": _cap(reply.get("text"))})
        messages.append({"role": "assistant", "content": reply.get("text") or "", "tool_calls": reply["tool_calls"]})

        if not reply["tool_calls"]:
            # 正文里写了 JSON 就当提交；否则提醒一次，再不行就是形状不对
            try:
                obj = llm.parse_json_reply(reply.get("text") or "")
                reply["tool_calls"] = [{"id": "tc_text", "name": "submit_offer",
                                        "arguments": {"ranked": obj.get("ranked"), "why": obj.get("why", ""), "evidence": obj.get("evidence")}}]
            except Exception:
                if nudged:
                    raise AgentFailed("bad_output", "no tool call and no JSON after a reminder")
                nudged = True
                messages.append({"role": "user", "content": "请通过工具行动：需要信息就调用 retrieve_history，准备好了就调用 submit_offer 提交。"})
                continue

        for call in reply["tool_calls"]:
            name, args = call.get("name", ""), call.get("arguments") or {}
            t1 = clock()
            counts["tool_calls"] += 1
            if name == "retrieve_history":
                if counts["retrieve"] >= budget["retrieve"]:
                    result = {"ok": False, "errors": [{"code": "BUDGET_EXCEEDED", "detail": f"retrieve_history allowed {budget['retrieve']} times"}]}
                else:
                    counts["retrieve"] += 1
                    kw = {k: args.get(k) for k in ("family", "dimension", "feedback_type") if args.get(k)}
                    result = retrieve_history(ctx, limit=args.get("limit", 2), **kw)
                record_tool(name, args, result, "model", model_call_id, clock() - t1)
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": _compact(result)})
            elif name == "validate_offer":
                if counts["validate"] >= budget["validate"]:
                    result = {"ok": False, "errors": [{"code": "BUDGET_EXCEEDED", "detail": f"validate_offer allowed {budget['validate']} times"}]}
                else:
                    counts["validate"] += 1
                    result = validate_offer(ctx, args.get("ranked"), args.get("evidence"))
                record_tool(name, args, result, "model", model_call_id, clock() - t1)
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": _compact(result)})
            elif name == "submit_offer":
                counts["submit"] += 1
                counts["runtime_validate"] += 1
                # 最终提交永远由后端再做一次共同的硬校验：模型可以不做 validate_offer，不能绕过这里
                result = validate_offer(ctx, args.get("ranked"), args.get("evidence"))
                record_tool("validate_offer", {"ranked": args.get("ranked"), "evidence": args.get("evidence"), "via": "submit_offer"},
                            result, "runtime", model_call_id, clock() - t1)
                if result["ok"]:
                    return {"ranked": list(args.get("ranked") or []), "why": str(args.get("why") or ""),
                            "evidence": list(args.get("evidence") or []),
                            "agent": {"trace": trace, "counts": counts, "stopped": "submitted",
                                      "seconds": round(clock() - t0, 2), "budget": budget}}
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                                 "content": _compact({"accepted": False, "errors": result["errors"], "hint": "修正后再提交"})})
                break      # 这一轮后面的工具调用不再执行：先改错
            else:
                result = {"ok": False, "errors": [{"code": "UNKNOWN_TOOL", "detail": name}]}
                record_tool(name or "?", args, result, "model", model_call_id, clock() - t1)
                messages.append({"role": "tool", "tool_call_id": call.get("id") or "tc_?", "name": name, "content": _compact(result)})
