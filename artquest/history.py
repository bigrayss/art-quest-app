"""User behavioural history → User Representation.

The pipeline this app exists to support is

    User → multiple drawing tasks → fine-grained process logging
         → user behavioural history → a new task → prediction / personalisation

and this module is the middle arrow. It turns a participant's finished sessions
into one compact structure that a personaliser — a template today, a model later
— can consume, and that a researcher can hold constant across conditions.

Two rules make it research-grade rather than a convenience cache:

1. **Always recomputed, never the only copy.** Nothing here is stored as
   authoritative state; the representation is derived from the logs on every
   call, so improving the builder retroactively improves every past participant
   and no session is stuck with an old summary.
2. **What the system saw at decision time is itself data.** When a session
   actually uses a representation, that exact snapshot is frozen into the
   session directory (`personalization.json`). Recomputing later would give a
   different, better answer — and then no one could reproduce the decision.

It reads the **event log**, not the stroke log: every `STROKE` / `ERASE` event
already carries `tool`, `color`, `size` and point count, so a participant's
whole history costs a few small files instead of megabytes of coordinates.
"""
import statistics
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config
from .logstore import read_json
from .reconstruct import read_jsonl, visible_ids
from .scoring.base import DIM_KEYS
from .storage import now_iso

# Bumped when the shape below changes, so a frozen snapshot stays readable.
REPRESENTATION_SCHEMA = 1
BUILDER = "baseline-v1"   # the non-model baseline; a learned one replaces this name


# -- locating a participant's sessions --------------------------------------
def _identity(meta: Dict[str, Any]) -> Tuple[str, str]:
    p = meta.get("participant")
    if isinstance(p, str):        # legacy free-text field
        return "", ""
    p = p or {}
    return p.get("anon_id", ""), p.get("participant_id", "")


def iter_sessions(root=None) -> Iterable[Dict[str, Any]]:
    for d in sorted((root or config.SESSIONS_DIR).iterdir()):
        if not d.is_dir():
            continue
        meta = read_json(d / "metadata.json")
        if meta:
            yield meta


def sessions_for(participant_id: str = "", anon_id: str = "",
                 *, finished_only: bool = True, before: str = "") -> List[Dict[str, Any]]:
    """A participant's sessions, oldest first.

    **The researcher code wins when there is one.** The device id is a fallback
    for free play, not a second name for the same child: a shared lab machine
    gives twenty children one `anon_id`, and matching on either id would merge
    their histories into one imaginary participant. So a code narrows to that
    code alone, and `anon_id` is consulted only when no code was given.

    `before` takes an ISO timestamp and keeps history strictly prior to it,
    which is what makes a representation reproducible after the fact: rebuild it
    with the start time of the session that used it and you get the same input
    the system had.
    """
    want_pid, want_anon = (participant_id or "").strip(), (anon_id or "").strip()
    if not (want_pid or want_anon):
        return []
    out = []
    for meta in iter_sessions():
        anon, pid = _identity(meta)
        if want_pid:
            if pid != want_pid:
                continue
        elif anon != want_anon:
            continue
        if finished_only and meta.get("status") != "done":
            continue
        if before and (meta.get("created_at") or "") >= before:
            continue
        out.append(meta)
    # id breaks ties so the order is stable whatever the filesystem hands back
    return sorted(out, key=lambda m: (m.get("created_at") or "", m.get("id") or ""))


# -- one finished task, compacted -------------------------------------------
def _process_from_events(sid: str) -> Dict[str, Any]:
    """Everything the event timeline can say about how the drawing was made."""
    events = read_jsonl(config.SESSIONS_DIR / sid / "events.jsonl")
    tools: Dict[str, int] = {}
    colors: Dict[str, int] = {}
    counts = {"stroke": 0, "erase": 0, "undo": 0, "redo": 0, "clear": 0,
              "zoom": 0, "pan": 0, "reference_open": 0}
    pauses: List[int] = []
    ref_ms, ref_open_at = 0, None
    zoom_max, zoomed_strokes, at_zoom = 1.0, 0, 1.0

    for e in events:
        kind, p = e.get("type"), e.get("payload") or {}
        if kind == "STROKE" or kind == "ERASE":
            counts["stroke" if kind == "STROKE" else "erase"] += 1
            if p.get("tool"):
                tools[p["tool"]] = tools.get(p["tool"], 0) + 1
            if p.get("color"):
                colors[p["color"]] = colors.get(p["color"], 0) + 1
            if at_zoom > 1.0:
                zoomed_strokes += 1
        elif kind in ("UNDO", "REDO", "CLEAR"):
            counts[kind.lower()] += 1
        elif kind == "ZOOM":
            counts["zoom"] += 1
            at_zoom = float(p.get("to") or 1.0)
            zoom_max = max(zoom_max, at_zoom)
        elif kind == "PAN":
            counts["pan"] += 1
        elif kind == "IDLE_END":
            pauses.append(int(p.get("duration_ms") or 0))
        elif kind == "REFERENCE_OPEN":
            counts["reference_open"] += 1
            ref_open_at = e.get("t_ms") or 0
        elif kind == "REFERENCE_CLOSE" and ref_open_at is not None:
            ref_ms += max(0, (e.get("t_ms") or 0) - ref_open_at)
            ref_open_at = None

    drawn = counts["stroke"] + counts["erase"]
    visible = visible_ids(events)
    return {
        "strokes": drawn,
        "strokes_visible": len(visible) if visible is not None else drawn,
        "strokes_removed": (drawn - len(visible)) if visible is not None else 0,
        "erase": counts["erase"],
        "undo": counts["undo"], "redo": counts["redo"], "clear": counts["clear"],
        "tools": tools, "n_tools": len(tools), "n_colors": len(colors),
        "pauses": len(pauses), "pause_ms": sum(pauses),
        "longest_pause_ms": max(pauses) if pauses else 0,
        "zoom_gestures": counts["zoom"], "pan_gestures": counts["pan"],
        "zoom_max": round(zoom_max, 2), "strokes_while_zoomed": zoomed_strokes,
        "reference_opens": counts["reference_open"], "reference_ms": ref_ms,
    }


def _dims(record: Optional[Dict[str, Any]]) -> Dict[str, float]:
    dims = ((record or {}).get("scores") or {}).get("dims") or {}
    return {k: v.get("score") for k, v in dims.items() if isinstance(v, dict) and v.get("score") is not None}


def task_record(meta: Dict[str, Any]) -> Dict[str, Any]:
    """One finished task as the representation carries it."""
    sid = meta.get("id") or meta.get("session_id")
    q = meta.get("questionnaire") or {}
    return {
        "session_id": sid,
        "task_id": meta.get("quest_id"),
        "category": (meta.get("task") or {}).get("category"),
        "difficulty": (meta.get("task") or {}).get("difficulty"),
        "focus_dims": (meta.get("task") or {}).get("focus_dims", []),
        "order_index": (meta.get("task") or {}).get("order_index"),
        "at": meta.get("created_at"),
        "duration_ms": (meta.get("times") or {}).get("duration_ms"),
        "revised": meta.get("revised"),
        # the condition matters: behaviour under a time limit is not the same child
        "condition": dict(meta.get("condition") or {}),
        "intent": (meta.get("intent") or {}).get("text", ""),
        "emotion": (meta.get("intent") or {}).get("emotion", ""),
        "process": _process_from_events(sid),
        "scores": {"before": _dims(meta.get("before")), "after": _dims(meta.get("after"))},
        "self_report": {k: q.get(k) for k in ("difficulty", "confidence", "enjoyment", "hardest_part")},
        "qc_ok": (meta.get("qc") or {}).get("ok"),
    }


# -- the representation ------------------------------------------------------
def _mean(values: List[float]) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.fmean(vals), 3) if vals else None


def _dim_trajectory(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-dimension: where the child lands, and which way it is moving.

    Deliberately thin — this is what a personaliser needs to decide something,
    not a substitute for analysing the score tables offline.
    """
    out = {}
    for key in DIM_KEYS:
        series = [t["scores"]["after"].get(key, t["scores"]["before"].get(key)) for t in tasks]
        series = [v for v in series if isinstance(v, (int, float))]
        if not series:
            continue
        out[key] = {"mean": _mean(series), "latest": series[-1], "n": len(series),
                    "delta": round(series[-1] - series[0], 3) if len(series) > 1 else 0.0}
    return out


def build(participant_id: str = "", anon_id: str = "", *, before: str = "") -> Dict[str, Any]:
    """Build a participant's representation from their finished sessions.

    Pure: reads the logs, writes nothing. Pass `before` to rebuild the exact
    input a past decision had.
    """
    metas = sessions_for(participant_id, anon_id, before=before)
    tasks = [task_record(m) for m in metas]
    rep = {
        "schema": REPRESENTATION_SCHEMA,
        "builder": BUILDER,
        "built_at": now_iso(),
        "participant": {"participant_id": participant_id, "anon_id": anon_id},
        "window": {"from": tasks[0]["at"] if tasks else None,
                   "to": tasks[-1]["at"] if tasks else None, "before": before or None},
        "n_tasks": len(tasks),
        "source_sessions": [t["session_id"] for t in tasks],
        "tasks": tasks,
    }
    if not tasks:
        # A cold-start child is a first-class case, not an error: the personaliser
        # must be able to tell "no history" apart from "history says nothing".
        rep.update({"cold_start": True, "process": {}, "dims": {}, "self_report": {}, "coverage": {}})
        return rep

    procs = [t["process"] for t in tasks]
    tools: Dict[str, int] = {}
    for p in procs:
        for tool, n in p["tools"].items():
            tools[tool] = tools.get(tool, 0) + n
    durations = [t["duration_ms"] for t in tasks if t["duration_ms"]]
    rep.update({
        "cold_start": False,
        "process": {
            "strokes_mean": _mean([p["strokes"] for p in procs]),
            "strokes_removed_total": sum(p["strokes_removed"] for p in procs),
            "undo_per_task": _mean([p["undo"] for p in procs]),
            "duration_ms_mean": _mean(durations),
            "pause_share": _mean([p["pause_ms"] / d for p, d in zip(procs, durations) if d]) if durations else None,
            "longest_pause_ms": max((p["longest_pause_ms"] for p in procs), default=0),
            "tools": tools,
            "n_colors_mean": _mean([p["n_colors"] for p in procs]),
            "zoom_used": any(p["zoom_gestures"] for p in procs),
            "zoom_max": max((p["zoom_max"] for p in procs), default=1.0),
            "reference_ms_total": sum(p["reference_ms"] for p in procs),
            "revised_share": _mean([1.0 if t["revised"] else 0.0 for t in tasks]),
        },
        "dims": _dim_trajectory(tasks),
        "self_report": {k: _mean([t["self_report"].get(k) for t in tasks])
                        for k in ("difficulty", "confidence", "enjoyment")},
        "coverage": {
            "task_ids": sorted({t["task_id"] for t in tasks if t["task_id"]}),
            "categories": sorted({t["category"] for t in tasks if t["category"]}),
            "tools": sorted(tools),
            "hardest_parts": [t["self_report"].get("hardest_part") for t in tasks
                              if t["self_report"].get("hardest_part")],
        },
    })
    return rep


def strongest_weakest(rep: Dict[str, Any], n: int = 2) -> Tuple[List[str], List[str]]:
    """Dimension keys the child scores highest / lowest on, best effort."""
    dims = rep.get("dims") or {}
    ranked = sorted((k for k in dims if dims[k].get("mean") is not None),
                    key=lambda k: dims[k]["mean"], reverse=True)
    return ranked[:n], list(reversed(ranked[-n:]))
