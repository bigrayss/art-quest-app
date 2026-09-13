"""Per-task rubric contract over the KidsArtBench 9 dimensions.

A task does not merely "target some dimensions". It declares, for every one of
the nine, which of four things it is:

    primary       the task is built to elicit this; it is what the task measures
    secondary     reliably observable here, but not what the task is for
    exploratory   collected without a strong prior; look, do not conclude
    not_applicable the task cannot elicit it at all

The rule that makes this worth having a type for:

    **N/A is not a low score.**

A black-and-white line task cannot produce colour richness. Recording that as 1
would say "this child uses colour poorly" — a claim the task never tested — and
that 1 would then average into their profile, into the model's training data and
into any comparison across tasks. So a not-applicable dimension carries `None`
and a reason, and `applicable()` is the only list a scorer or a rater is ever
offered.

Dimension names and the scale stay exactly as KidsArtBench defines them
(`scoring/base.py`); a task chooses which of them apply, never what they mean.
"""
from typing import Any, Dict, Iterable, List, Optional

from .scoring.base import DIM_KEYS

ROLES = ("primary", "secondary", "exploratory", "not_applicable")
SCORED_ROLES = ("primary", "secondary", "exploratory")
RUBRIC_VERSION = "kidsartbench-9d/1"


class RubricError(ValueError):
    pass


def normalize(spec: Optional[Dict[str, Any]], *, task_id: str = "") -> Dict[str, Any]:
    """Validate a task's rubric block and fill in the roles it left out.

    Anything the task does not mention is `exploratory`: collected, but with no
    claim attached. Silence must not become an implicit N/A — dropping a
    dimension by accident would quietly stop measuring it.
    """
    spec = dict(spec or {})
    seen: Dict[str, str] = {}
    for role in ROLES:
        for key in spec.get(f"{role}_dimensions", []) or []:
            if key not in DIM_KEYS:
                raise RubricError(f"{task_id or '<task>'}: unknown dimension {key!r}")
            if key in seen:
                raise RubricError(
                    f"{task_id or '<task>'}: {key!r} is both {seen[key]} and {role}")
            seen[key] = role

    out = {f"{role}_dimensions": [k for k in DIM_KEYS if seen.get(k) == role] for role in ROLES}
    out["exploratory_dimensions"] += [k for k in DIM_KEYS if k not in seen]
    out["version"] = spec.get("version", RUBRIC_VERSION)
    out["na_reason"] = dict(spec.get("na_reason") or {})
    missing = [k for k in out["not_applicable_dimensions"] if k not in out["na_reason"]]
    if missing:
        # an unexplained N/A is indistinguishable from a forgotten dimension
        raise RubricError(f"{task_id or '<task>'}: not_applicable needs a reason: {missing}")
    return out


def role_of(rubric: Dict[str, Any], dim: str) -> str:
    for role in ROLES:
        if dim in (rubric.get(f"{role}_dimensions") or []):
            return role
    return "exploratory"


def applicable(rubric: Optional[Dict[str, Any]]) -> List[str]:
    """The only dimensions a scorer or a rater should ever be shown."""
    if not rubric:
        return list(DIM_KEYS)
    na = set(rubric.get("not_applicable_dimensions") or [])
    return [k for k in DIM_KEYS if k not in na]


def apply_contract(scores: Dict[str, Any], rubric: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Mark every dimension with its role and blank the ones the task cannot test.

    A backend that scored a not-applicable dimension anyway does not get to keep
    the number: it was produced without the conditions that give it meaning.
    """
    rubric = rubric or {}
    na_reason = rubric.get("na_reason") or {}
    dims = dict(scores.get("dims") or {})
    for key in DIM_KEYS:
        role = role_of(rubric, key) if rubric else "exploratory"
        entry = dict(dims.get(key) or {})
        if role == "not_applicable":
            entry = {"score": None, "role": role,
                     "note": na_reason.get(key, "这个任务无法考察这个维度"),
                     "na": True}
        elif entry:
            entry["role"] = role
            entry["na"] = False
        else:
            continue
        dims[key] = entry
    out = dict(scores)
    out["dims"] = dims
    out["rubric_version"] = rubric.get("version", RUBRIC_VERSION)
    out["applicable"] = applicable(rubric)
    return out


def summary(rubric: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    rubric = rubric or {}
    return {role: list(rubric.get(f"{role}_dimensions") or []) for role in ROLES}


def check_rating(dims: Iterable[str], rubric: Optional[Dict[str, Any]]) -> List[str]:
    """Dimensions a human rater tried to score that this task cannot test."""
    na = set((rubric or {}).get("not_applicable_dimensions") or [])
    return sorted(set(dims) & na)
