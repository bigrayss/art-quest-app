"""Per-task rubric contract over the KidsArtBench 9 dimensions.

**Every drawing is scored on all nine.** A drawing has a composition, a line
quality and a use of colour whatever it was made for, so those are always
measured. What a task's rubric says is only which dimensions it is *additionally*
built to elicit:

    primary       the task is built to elicit this; it is what the task measures
    secondary     reliably observable here, but not what the task is for
    exploratory   scored like the rest, with no prior attached  ← the default
    not_applicable the task's own condition makes this impossible to produce

`primary` does not narrow what gets scored. It drives the focus in the UI, the
"what this mission trained" line, and which of 彩点's attributes grow — never
whether a number is produced.

`not_applicable` is the one exception, and it is deliberately hard to reach:

    **N/A is not a low score — and "we are not interested in it" is not N/A.**

Recording colour richness as 1 for a task that could not produce colour would
say "this child uses colour poorly", a claim the task never tested, and that 1
would then average into their profile, into training data and into every
cross-task comparison. But the opposite mistake is just as bad: dropping a
dimension because the task is "not about" it silently stops measuring something
the drawing plainly has.

So a task may not simply declare a dimension N/A. `normalize()` derives N/A from
the task's **condition** and refuses any declaration the condition does not
justify. Today nothing in the library reaches it: the colour palette is offered
in every task — `allowed_tools` restricts the four brush buttons, and the pencil
still paints in whichever colour the child picked — so even a "pencil only" task
is a task in which colour can be measured.

Dimension names and the scale stay exactly as KidsArtBench defines them
(`scoring/base.py`); a task chooses which of them it focuses on, never what they
mean and never whether they are recorded.
"""
from typing import Any, Dict, Iterable, List, Optional

from .scoring.base import DIM_KEYS

ROLES = ("primary", "secondary", "exploratory", "not_applicable")
SCORED_ROLES = ("primary", "secondary", "exploratory")
RUBRIC_VERSION = "kidsartbench-9d/2"

# Tools that put the child's chosen colour on the canvas. The pencil is one of
# them: `allowed_tools` disables brush buttons, never the palette.
COLOUR_TOOLS = ("pencil", "brush", "marker")
COLOUR_DIMS = ("color_richness", "color_contrast")
_NO_COLOUR_REASON = "这个任务不提供任何能上色的工具，画面里不会出现颜色"


class RubricError(ValueError):
    pass


def condition_na(allowed_tools: Optional[Iterable[str]]) -> Dict[str, str]:
    """Dimensions this task's own condition makes impossible, and why.

    The only such condition today is a task that offers no colour-capable tool
    at all. It is derived rather than declared on purpose: N/A has to be a
    consequence of the setup, never a way to opt out of measuring something.
    """
    if allowed_tools is None:
        return {}
    tools = set(allowed_tools)
    if tools & set(COLOUR_TOOLS):
        return {}
    return {dim: _NO_COLOUR_REASON for dim in COLOUR_DIMS}


def normalize(spec: Optional[Dict[str, Any]], *, task_id: str = "",
              allowed_tools: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Validate a task's rubric block and fill in the roles it left out.

    Anything the task does not mention is `exploratory`: **scored**, with no
    claim attached. Silence must not become an implicit N/A — dropping a
    dimension by accident would quietly stop measuring it.

    `not_applicable` may only contain what `condition_na(allowed_tools)` derives.
    A task that simply is not interested in a dimension still has it scored.
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

    derived = condition_na(allowed_tools)
    unjustified = sorted(k for k in (seen.get(k) == "not_applicable" and k for k in seen)
                         if k and k not in derived)
    if unjustified:
        raise RubricError(
            f"{task_id or '<task>'}: {unjustified} cannot be not_applicable — every dimension is "
            "scored unless the task's own condition makes it impossible to produce. "
            "A task that is merely not about a dimension still has it measured.")
    for key in derived:
        seen[key] = "not_applicable"

    out = {f"{role}_dimensions": [k for k in DIM_KEYS if seen.get(k) == role] for role in ROLES}
    out["exploratory_dimensions"] += [k for k in DIM_KEYS if k not in seen]
    out["version"] = spec.get("version", RUBRIC_VERSION)
    out["na_reason"] = {**dict(spec.get("na_reason") or {}), **derived}
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
