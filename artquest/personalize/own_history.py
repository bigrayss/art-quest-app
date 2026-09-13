"""The User History arm: the child's own record, read by a template, no model.

This is the baseline a learned personaliser has to beat. Everything it says is
traceable to a number in the representation, which also makes it the reference
implementation of what a model-backed arm is allowed to use.
"""
from typing import Any, Dict, List, Optional

from ..history import strongest_weakest
from ..scoring.base import DIMENSIONS
from .base import PREDICTED_KEYS, PRIOR, clamp, result

_ZH = {d["key"]: d["zh"] for d in DIMENSIONS}
_TOOL_ZH = {"pencil": "铅笔", "brush": "笔刷", "marker": "马克笔", "eraser": "橡皮"}


def _predict(task: Dict[str, Any], rep: Dict[str, Any]) -> Dict[str, Any]:
    """Prior self-reports, shifted by how much harder this task is than those."""
    self_report = rep.get("self_report") or {}
    tasks = rep.get("tasks") or []
    prior_diff = [t.get("difficulty") for t in tasks if isinstance(t.get("difficulty"), (int, float))]
    shift = 0.0
    if prior_diff and isinstance(task.get("difficulty"), (int, float)):
        shift = (task["difficulty"] - sum(prior_diff) / len(prior_diff)) * 0.5
    out = {}
    for key in PREDICTED_KEYS:
        base = self_report.get(key)
        if base is None:
            out[key] = PRIOR
        else:
            # a harder task reads as harder and less certain
            out[key] = clamp(base + (shift if key == "difficulty" else -shift))
    _, weakest = strongest_weakest(rep)
    out["weakest_dims"] = weakest
    out["basis"] = (f"{len(tasks)} prior task(s); difficulty shift {shift:+.2f}"
                    if tasks else "no prior tasks")
    return out


def _shown(task: Dict[str, Any], rep: Dict[str, Any]) -> List[Dict[str, str]]:
    """Short, factual lines about the child's own past work — never a score."""
    lines: List[Dict[str, str]] = []
    proc = rep.get("process") or {}
    n = rep.get("n_tasks", 0)
    cov = rep.get("coverage") or {}

    tools = "、".join(_TOOL_ZH.get(t, t) for t in (cov.get("tools") or []))
    lines.append({"kind": "recap", "text": f"你已经完成了 {n} 次创作"
                  + (f"，用过{tools}" if tools else "") + "。"})
    strong, weak = strongest_weakest(rep, n=1)
    if strong:
        lines.append({"kind": "strength", "text": f"你在「{_ZH.get(strong[0], strong[0])}」上一直很使得上劲，这次也可以放心用它。"})
    if weak and weak[0] in (task.get("focus_dims") or []):
        lines.append({"kind": "focus", "text": f"这一关正好会用到「{_ZH.get(weak[0], weak[0])}」——上次这里你花了点力气，慢慢来。"})
    if proc.get("longest_pause_ms", 0) > 60_000:
        lines.append({"kind": "habit", "text": "你习惯先停下来想一会儿再动笔，这次也不用急。"})
    if cov.get("hardest_parts"):
        lines.append({"kind": "recall", "text": f"上次你说最难的是「{cov['hardest_parts'][-1]}」。"})
    return lines[:3]


class OwnHistory:
    name = "own_history"
    uses_history = True

    def __init__(self, requested: str = "history", note: str = ""):
        # may stand in for the `personalized` arm when no model is configured —
        # recorded, never silent
        self.requested, self.note = requested, note

    def prepare(self, task: Dict[str, Any], rep: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        available = self.requested == "history"
        if not rep or rep.get("cold_start"):
            return result(self.name, requested=self.requested, rep=rep, available=available,
                          shown=[{"kind": "recap", "text": "这是你的第一次创作，慢慢来。"}],
                          prediction=dict({k: PRIOR for k in PREDICTED_KEYS},
                                          weakest_dims=[], basis="cold start: no finished task yet"),
                          note=self.note or "cold start")
        return result(self.name, requested=self.requested, rep=rep, available=available,
                      shown=_shown(task, rep), prediction=_predict(task, rep), note=self.note)
