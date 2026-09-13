"""The Personalized Model arm: a model reads the representation.

It is given the *representation*, never the raw logs — the same input the
template arm gets, so the comparison isolates the model rather than the amount
of data. Its output is constrained to the same shape, so an arm can be swapped
without touching the session record or the analysis.

Replace this with the real personalisation model by implementing `prepare()`
and registering it in `get_personalizer()`.
"""
import json
import logging
from typing import Any, Dict, Optional

from ..history import strongest_weakest
from ..llm import claude_json
from ..scoring.base import DIMENSIONS, SCALE_MAX
from .base import PREDICTED_KEYS, PRIOR, clamp, result

log = logging.getLogger("artquest")
_ZH = {d["key"]: d["zh"] for d in DIMENSIONS}

SYSTEM = """你拿到的是一位 8–14 岁创作者过往创作过程的结构化摘要，以及他即将开始的新任务。
你的工作有两件，互不干扰：

1. `shown`：写 1–3 条**给这个孩子看**的短句（每条不超过 30 字）。硬性原则与美术教练一致——
   帮助思考、不替代创作、不给标准答案、不提分数、不评判好坏。只引用摘要里真实存在的事实
   （做过几次、用过什么工具、上次说最难的是什么、停顿习惯等），不要编造。
2. `prediction`：预测这个孩子**做完这次任务后**会怎样自评（1–5）：`difficulty` 有多难、
   `confidence` 有多有把握；并指出他这次最可能吃力的 1–2 个维度 `weakest_dims`。
   这部分是给研究者的，不会展示给孩子。`basis` 用一句话说明你依据摘要里的哪些信息。

只输出 JSON。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "shown": {"type": "array", "maxItems": 3, "items": {
            "type": "object",
            "properties": {"kind": {"type": "string"}, "text": {"type": "string"}},
            "required": ["kind", "text"], "additionalProperties": False}},
        "prediction": {"type": "object", "properties": {
            "difficulty": {"type": "number", "minimum": 1, "maximum": SCALE_MAX},
            "confidence": {"type": "number", "minimum": 1, "maximum": SCALE_MAX},
            "weakest_dims": {"type": "array", "maxItems": 2, "items": {"type": "string"}},
            "basis": {"type": "string"}},
            "required": ["difficulty", "confidence", "weakest_dims", "basis"],
            "additionalProperties": False},
    },
    "required": ["shown", "prediction"],
    "additionalProperties": False,
}


def _digest(rep: Dict[str, Any]) -> Dict[str, Any]:
    """What the model is allowed to see: the representation, minus the bulk."""
    return {
        "n_tasks": rep.get("n_tasks"),
        "process": rep.get("process"),
        "self_report": rep.get("self_report"),
        "coverage": rep.get("coverage"),
        "dims": {_ZH.get(k, k): v for k, v in (rep.get("dims") or {}).items()},
        "tasks": [{k: t.get(k) for k in ("task_id", "category", "difficulty", "at",
                                         "duration_ms", "revised", "self_report", "emotion")}
                  for t in (rep.get("tasks") or [])],
    }


class ClaudePersonalizer:
    name = "claude"
    uses_history = True

    def prepare(self, task: Dict[str, Any], rep: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not rep or rep.get("cold_start"):
            # nothing to personalise on; say so rather than inventing a history
            return result(self.name, requested="personalized", rep=rep,
                          shown=[{"kind": "recap", "text": "这是你的第一次创作，慢慢来。"}],
                          prediction=dict({k: PRIOR for k in PREDICTED_KEYS},
                                          weakest_dims=[], basis="cold start: no finished task yet"),
                          note="cold start")
        prompt = (
            f"新任务：{task.get('title')} —— {task.get('prompt')}\n"
            f"任务类别：{task.get('category')}，难度：{task.get('difficulty')}，"
            f"重点维度：{'、'.join(_ZH.get(k, k) for k in (task.get('focus_dims') or []))}\n\n"
            f"这个孩子的过往摘要：\n{json.dumps(_digest(rep), ensure_ascii=False, indent=2)}"
        )
        out = claude_json(SYSTEM, [{"type": "text", "text": prompt}], SCHEMA)
        pred = dict(out.get("prediction") or {})
        for key in PREDICTED_KEYS:
            pred[key] = clamp(pred.get(key, PRIOR))
        _, weakest = strongest_weakest(rep)
        pred.setdefault("weakest_dims", weakest)
        return result(self.name, requested="personalized", rep=rep,
                      shown=list(out.get("shown") or [])[:3], prediction=pred)
