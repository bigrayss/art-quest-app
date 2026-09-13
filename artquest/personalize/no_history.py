"""The control arm: the system is told nothing about this child."""
from typing import Any, Dict, Optional

from .base import PREDICTED_KEYS, PRIOR, result


class NoHistory:
    name = "none"
    uses_history = False

    def prepare(self, task: Dict[str, Any], rep: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        # `rep` is deliberately ignored — and the record says so, so a later
        # reader can tell "saw nothing" apart from "had nothing to see".
        return result(self.name, requested="none", shown=[],
                      prediction=dict({k: PRIOR for k in PREDICTED_KEYS},
                                      weakest_dims=[], basis="population prior, no history consulted"),
                      rep=None,
                      note="control arm: representation not consulted")
