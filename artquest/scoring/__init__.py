"""KidsArtBench 9-dimension scoring interface (pluggable backends).

Stage 1 goal (guide §02): "能稳定调用并呈现结果". Backends:
  * claude     — Claude vision rates the 9 dimensions with structured JSON output
  * heuristic  — offline PIL statistics; only colour/line/layout dims are meaningful
Replace/extend with the official KidsArtBench model by adding a class that
implements `Scorer` and registering it in `get_scorer()`.
"""
from ..config import SCORER_BACKEND, resolve_backend
from .base import DIMENSIONS, SCALE_MAX, Scorer


def get_scorer() -> Scorer:
    backend = resolve_backend(SCORER_BACKEND, "claude", "heuristic")
    if backend == "claude":
        from .claude_scorer import ClaudeScorer
        return ClaudeScorer()
    from .heuristic_scorer import HeuristicScorer
    return HeuristicScorer()


__all__ = ["DIMENSIONS", "SCALE_MAX", "Scorer", "get_scorer"]
