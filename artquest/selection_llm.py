"""模型排序臂（agent 级数据计划 PR 5，2026-10-15）：在**同一个选题位置**上，把「自由位补哪一道」从固定顺序换成模型排序。

规则臂（rules）照旧；这里只在协议把这条 session 分到 `selection_policy=llm` 时才被调用，而且只在
服务端是选题权威、孩子已经有历史、而且是上一张画完/放弃**之后预算**的时候（地图加载路径上从不等模型）。

契约（三臂共用，见 selection.apply_policy）：候选集合是冻结的，模型只在池子里排序、只填自由位；
越界 / 重复 / 数量不够 → 整个回退规则并记 fallback_reason。输入是 history.build 的 representation
（和个性化那一臂同一份口径），不另造画像。调用本身走 llm.recording（purpose=select），进那张决策票的
calls.jsonl，票变成 session 时一起带走。
"""
import json
from typing import Any, Dict, List, Optional

from . import llm
from .quests import QUESTS_BY_ID

PROMPT_VERSION = "select/v1"

SYSTEM = (
    "你是一个儿童美术练习的任务编排助手。你会拿到一个孩子最近几次创作的摘要（九个维度的评分走向、"
    "做过的任务、修改意愿），和一组候选任务（每道都附家族、题面、主要考察的维度）。\n"
    "请从候选里挑出接下来最适合这个孩子的几道，按推荐顺序排好。原则：\n"
    "1. 只能从候选列表里选，输出任务 id 原样照抄，不要编造、不要重复。\n"
    "2. 优先练这个孩子最近偏弱、但不是一直很弱的维度；连续几次同一家族的话换一换。\n"
    "3. 不要因为分数低就只给简单的——孩子刚修改过、分数在涨的维度，可以给一道更有挑战的。\n"
    "4. 不解释给孩子看，why 是给研究员的一句话。\n"
    "只输出 JSON。"
)

SCHEMA = {
    "type": "object",
    "properties": {
        "ranked": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
        "why": {"type": "string"},
    },
    "required": ["ranked", "why"],
    "additionalProperties": False,
}


def digest(rep: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """模型能看到的那份：representation 去掉大块（每道题的原始记录只留几个字段）。和个性化臂同一口径。"""
    rep = rep or {}
    return {
        "n_tasks": rep.get("n_tasks"),
        "dims": rep.get("dims"),
        "process": rep.get("process"),
        "self_report": rep.get("self_report"),
        "tasks": [{k: t.get(k) for k in ("task_id", "category", "at", "revised", "duration_ms")}
                  for t in (rep.get("tasks") or [])][-8:],
    }


def describe(task_id: str) -> Dict[str, Any]:
    q = QUESTS_BY_ID.get(task_id) or {}
    return {"id": task_id, "family": q.get("family", ""), "family_name": q.get("family_name", ""),
            "title": q.get("title", ""), "prompt": (q.get("prompt") or "")[:160],
            "primary_dimensions": list((q.get("rubric") or {}).get("primary_dimensions") or [])}


def rank(decision: Dict[str, Any], pool: List[str], n: int, rep: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """问一次模型：在池子里排出前 n 道。返回 {"ranked": [...], "why": "..."}；形状不对由 llm 层抛 LLMBadOutput。"""
    prompt = (
        f"需要排出 {n} 道（可以多给几道备选，按顺序）。\n\n"
        f"这个孩子的过往摘要：\n{json.dumps(digest(rep), ensure_ascii=False, indent=1)}\n\n"
        f"候选任务：\n{json.dumps([describe(t) for t in pool], ensure_ascii=False, indent=1)}\n\n"
        f"规则臂原本会按固定顺序给：{json.dumps(decision.get('rules_fill') or [], ensure_ascii=False)}（仅供参考，不必照搬）。"
    )
    out = llm.claude_json(SYSTEM, [{"type": "text", "text": prompt}], SCHEMA, max_tokens=600)
    return {"ranked": [str(t) for t in (out.get("ranked") or [])], "why": str(out.get("why") or "")}
