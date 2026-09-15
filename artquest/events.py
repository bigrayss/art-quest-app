# -*- coding: utf-8 -*-
"""The unified event vocabulary — one timeline, one clock.

Every module writes into the same stream with the same clock, so nothing has to
be reconciled afterwards:

* `t_ms` is **the** timestamp: milliseconds since the session started drawing.
  Wall-clock time is recoverable from `metadata.times.started_at_ms + t_ms`, so
  no event carries its own wall clock and no two modules can disagree about
  what "now" was.
* Server-side records (feedback shown, session end) land in the same stream with
  the same `t_ms`, taken from the client's clock at the request that caused them.

Some names changed when the vocabulary was unified. Renaming without an alias
would orphan the sessions already collected, so `canonical()` folds the old name
onto the new one and every reader goes through it. Old logs keep their bytes;
readers stop caring.
"""
from typing import Any, Dict, Iterable, Set

# -- session / task ----------------------------------------------------------
SESSION_START = "SESSION_START"
TASK_SHOW = "TASK_SHOW"
CANVAS_GEOMETRY = "CANVAS_GEOMETRY"
TASK_SUBMIT = "TASK_SUBMIT"
SESSION_ABANDONED = "SESSION_ABANDONED"   # the child backed out before submitting
SESSION_END = "SESSION_END"

# -- drawing -----------------------------------------------------------------
STROKE_START = "STROKE_START"
STROKE_END = "STROKE_END"
ERASE = "ERASE"
UNDO = "UNDO"
REDO = "REDO"
CLEAR = "CLEAR"

# -- tools -------------------------------------------------------------------
BRUSH_CHANGE = "BRUSH_CHANGE"
COLOR_CHANGE = "COLOR_CHANGE"
SIZE_CHANGE = "SIZE_CHANGE"

# -- view --------------------------------------------------------------------
ZOOM = "ZOOM"
PAN = "PAN"

# -- reference ---------------------------------------------------------------
REFERENCE_SHOW = "REFERENCE_SHOW"        # presented by the task
REFERENCE_OPEN = "REFERENCE_OPEN"        # the child opened it
REFERENCE_CLOSE = "REFERENCE_CLOSE"
REFERENCE_ZOOM = "REFERENCE_ZOOM"
REFERENCE_PAN = "REFERENCE_PAN"
REFERENCE_FOCUS = "REFERENCE_FOCUS"      # attention moved to the reference
CANVAS_FOCUS = "CANVAS_FOCUS"            # …and back to the canvas

# -- attention ---------------------------------------------------------------
PAUSE_START = "PAUSE_START"
PAUSE_END = "PAUSE_END"
TIME_LIMIT_REACHED = "TIME_LIMIT_REACHED"

# -- feedback / revision -----------------------------------------------------
FEEDBACK_SHOW = "FEEDBACK_SHOW"
FEEDBACK_DISMISS = "FEEDBACK_DISMISS"
REVISION_START = "REVISION_START"
REVISION_SKIPPED = "REVISION_SKIPPED"
HISTORY_SHOWN = "HISTORY_SHOWN"
RATING_ADDED = "RATING_ADDED"

# -- outcome -----------------------------------------------------------------
QUESTIONNAIRE_SUBMITTED = "QUESTIONNAIRE_SUBMITTED"
DOWNLOAD = "DOWNLOAD"

# Old name -> unified name. Sessions recorded before the vocabulary settled keep
# their bytes; every reader folds them onto the current name.
ALIASES: Dict[str, str] = {
    "STROKE": STROKE_END,          # one record was written, at the end of the stroke
    "IDLE_START": PAUSE_START,
    "IDLE_END": PAUSE_END,
    "FEEDBACK_SHOWN": FEEDBACK_SHOW,
}

VOCABULARY: Set[str] = {
    SESSION_START, TASK_SHOW, CANVAS_GEOMETRY, TASK_SUBMIT, SESSION_ABANDONED, SESSION_END,
    STROKE_START, STROKE_END, ERASE, UNDO, REDO, CLEAR,
    BRUSH_CHANGE, COLOR_CHANGE, SIZE_CHANGE, ZOOM, PAN,
    REFERENCE_SHOW, REFERENCE_OPEN, REFERENCE_CLOSE, REFERENCE_ZOOM,
    REFERENCE_PAN, REFERENCE_FOCUS, CANVAS_FOCUS,
    PAUSE_START, PAUSE_END, TIME_LIMIT_REACHED,
    FEEDBACK_SHOW, FEEDBACK_DISMISS, REVISION_START, REVISION_SKIPPED,
    HISTORY_SHOWN, RATING_ADDED, QUESTIONNAIRE_SUBMITTED, DOWNLOAD,
}

# The strokes that actually put ink on the canvas, under either vocabulary.
DRAW_TYPES = (STROKE_END, ERASE)


def canonical(type_: str) -> str:
    """The unified name for an event type, old or new."""
    return ALIASES.get(type_, type_)


def is_known(type_: str) -> bool:
    return canonical(type_) in VOCABULARY


def unknown_types(types: Iterable[str]) -> Set[str]:
    """Event types not in the vocabulary — a module inventing its own name."""
    return {t for t in types if t and not is_known(t)}


# ---------------------------------------------------------------------------
# Strokes carry a vocabulary too, and it converged the same way event names did.
# ---------------------------------------------------------------------------
# What a raw stroke is, and nothing else:
#
#     geometry + time + tool state
#
# Anything derivable stays out of the record — `t_end_ms` is `t0_ms` plus the
# last point's `dt`, and speed / curvature / length belong to analysis. Two
# fields that look derivable are kept on purpose: `zoom` is what the child could
# see while drawing this stroke, and `pressure_supported` / `tilt_supported` say
# *why* a null is null — no sensor, rather than a sensor that read nothing.
STROKE_FIELDS = ("stroke_id", "seq", "phase", "op", "tool", "color", "size", "opacity",
                 "pointer", "pressure_supported", "tilt_supported", "zoom", "t0_ms", "points")
_STROKE_ALIASES = {"t_start_ms": "t0_ms", "pointer_type": "pointer"}


def canonical_stroke(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Fold an older stroke record onto the current field names.

    Same contract as `canonical()` for event names: the file on disk is never
    rewritten, every reader goes through here.
    """
    out = dict(rec)
    for old, new in _STROKE_ALIASES.items():
        if old in out:
            out.setdefault(new, out[old])
            out.pop(old)
    if "op" not in out:
        out["op"] = "erase" if out.pop("erase", False) else "draw"
    out.pop("erase", None)
    out.pop("t_end_ms", None)          # exactly t0_ms + points[-1][2]
    return out


def stroke_end_ms(rec: Dict[str, Any]) -> float:
    """When the pen came up — from the record, or from its last sample."""
    if rec.get("t_end_ms") is not None:
        return float(rec["t_end_ms"])
    t0 = float(rec.get("t0_ms") if rec.get("t0_ms") is not None else rec.get("t_start_ms") or 0)
    pts = rec.get("points") or []
    return t0 + float(pts[-1][2] or 0) if pts else t0


def stroke_start_ms(rec: Dict[str, Any]) -> float:
    """When the pen went down, under either spelling."""
    v = rec.get("t0_ms")
    return float(v if v is not None else (rec.get("t_start_ms") or 0))
