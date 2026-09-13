"""The three arms of the personalisation comparison, and what they must return.

    none          No History        — the control: the system is shown nothing
    history       User History      — the child's own representation, no model
    personalized  Personalized Model — a model reads the representation

The arm decides two separate things, and the split matters:

* **what the child sees** (`shown`) — the intervention being studied;
* **what the system predicts** (`prediction`) — recorded for *every* arm, so
  prediction accuracy is comparable across them. The `none` arm predicts from a
  population prior, which is exactly the baseline the other two must beat.

The prediction targets the child's own end-of-task self-report, because that is
the one label every session already produces. It is written down before the
child draws and scored against the answer afterwards (`outcome` / `error` in
`personalization.json`), which makes the comparison an evaluation rather than a
demo.
"""
from typing import Any, Dict, List, Optional, Protocol

from ..scoring.base import SCALE_MAX

MODES = ("none", "history", "personalized")
PRIOR = (1 + SCALE_MAX) / 2.0      # midpoint of the 1–5 scale: "no idea, assume typical"
PREDICTED_KEYS = ("difficulty", "confidence")


class Personalizer(Protocol):
    name: str
    uses_history: bool

    def prepare(self, task: Dict[str, Any], rep: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Return what to show the child and what the system predicts."""
        ...


def clamp(v: float) -> float:
    return round(max(1.0, min(float(SCALE_MAX), v)), 3)


def result(backend: str, *, requested: str, shown: Optional[List[Dict[str, str]]] = None,
           prediction: Optional[Dict[str, Any]] = None, rep: Optional[Dict[str, Any]] = None,
           available: bool = True, note: str = "") -> Dict[str, Any]:
    """One personalisation decision, in the shape that gets frozen into a session."""
    rep = rep or {}
    return {
        "requested_mode": requested,
        "backend": backend,                 # what actually ran — never assume it is the request
        "available": available,             # False when the requested arm could not run
        "note": note,
        "history_used": {
            "n_tasks": rep.get("n_tasks", 0),
            "cold_start": rep.get("cold_start", True),
            "source_sessions": rep.get("source_sessions", []),
            "builder": rep.get("builder"),
            "schema": rep.get("schema"),
        },
        "shown": shown or [],
        "prediction": prediction or {},
    }
