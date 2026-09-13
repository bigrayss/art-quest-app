"""Feedback → subsequent revision: did the child act on it, and where?

Requirement for the feedback experiments: `feedback content + timestamp +
source + target region + subsequent revision`. The first four are recorded when
the feedback happens; the fifth is not a field anyone can write down — it only
exists as a relation between a feedback record and the strokes that came after
it. This module computes that relation from data already on disk.

The number worth having is not "did they draw afterwards" (they always do, the
flow asks them to) but **whether they worked where the feedback pointed, more
than they had been**. So each feedback gets two windows — everything before it
was shown, and everything after — and the share of drawing that falls inside
its target region in each. `region_shift` is the difference.

Nothing is stored: this is derived from the logs on request, like the user
representation, so improving it improves every past session.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import events as ev
from .reconstruct import read_jsonl, visible_ids

# A feedback with no region can still be attributed in time, just not in space.
_NEEDS = {"rect": 4, "point": 3}


def inside(region: Optional[Dict[str, Any]], x: float, y: float) -> bool:
    """Is a canvas point inside a target region? False when there is no region."""
    if not region:
        return False
    shape, c = region.get("shape", "rect"), list(region.get("coords") or [])
    if shape in _NEEDS and len(c) != _NEEDS[shape]:
        return False
    if shape == "rect":
        return c[0] <= x <= c[0] + c[2] and c[1] <= y <= c[1] + c[3]
    if shape == "point":
        return (x - c[0]) ** 2 + (y - c[1]) ** 2 <= c[2] ** 2
    if shape == "poly" and len(c) >= 6 and len(c) % 2 == 0:
        pts = list(zip(c[0::2], c[1::2]))
        hit = False
        j = len(pts) - 1
        for i, (xi, yi) in enumerate(pts):          # ray casting
            xj, yj = pts[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
                hit = not hit
            j = i
        return hit
    return False


def _window(strokes: Sequence[Dict[str, Any]], region: Optional[Dict[str, Any]],
            lo_ms: Optional[int], hi_ms: Optional[int]) -> Dict[str, Any]:
    """Drawing activity in a time window, and how much of it lands in `region`."""
    n_strokes = n_points = in_strokes = in_points = 0
    for s in strokes:
        t = s.get("t_start_ms") or 0
        if lo_ms is not None and t < lo_ms:
            continue
        if hi_ms is not None and t >= hi_ms:
            continue
        pts = s.get("points") or []
        n_strokes += 1
        n_points += len(pts)
        if region:
            hits = sum(1 for p in pts if inside(region, p[0], p[1]))
            in_points += hits
            in_strokes += 1 if hits else 0
    out = {"strokes": n_strokes, "points": n_points}
    if region:
        out.update({"strokes_in_region": in_strokes, "points_in_region": in_points,
                    "share_in_region": round(in_points / n_points, 4) if n_points else None})
    return out


def attribute(session_dir: Path) -> Dict[str, Any]:
    """One record per feedback: when it landed, and what followed it."""
    d = Path(session_dir)
    feedback = read_jsonl(d / "feedback.jsonl")
    events = read_jsonl(d / "events.jsonl")
    strokes = read_jsonl(d / "strokes.jsonl")

    # only strokes still on the artwork count as revision — one the child drew
    # and immediately undid is not a response to feedback
    keep = visible_ids(events)
    if keep is not None:
        alive = set(keep)
        strokes = [s for s in strokes if s.get("stroke_id") in alive]
    strokes.sort(key=lambda s: s.get("t_start_ms") or 0)

    starts = {}   # feedback_id -> REVISION_START / REVISION_SKIPPED event
    for e in events:
        if ev.canonical(e.get("type")) in (ev.REVISION_START, ev.REVISION_SKIPPED):
            fid = (e.get("payload") or {}).get("feedback_id") or ""
            starts.setdefault(fid, e)

    shown = {}    # feedback_id -> the moment it was actually put on screen
    for e in events:
        if ev.canonical(e.get("type")) == ev.FEEDBACK_SHOW:
            fid = (e.get("payload") or {}).get("feedback_id")
            if fid:
                shown[fid] = e.get("t_ms") or 0

    ordered = sorted(feedback, key=lambda f: shown.get(f.get("feedback_id"), f.get("t_ms") or 0))
    out: List[Dict[str, Any]] = []
    for i, fb in enumerate(ordered):
        fid = fb.get("feedback_id")
        at = shown.get(fid, fb.get("t_ms") or 0)
        nxt = shown.get(ordered[i + 1].get("feedback_id"),
                        ordered[i + 1].get("t_ms") or 0) if i + 1 < len(ordered) else None
        region = fb.get("target_region")
        before, after = _window(strokes, region, None, at), _window(strokes, region, at, nxt)

        evt = starts.get(fid) or starts.get("")
        rec = {
            "feedback_id": fid,
            "source": fb.get("source"), "feedback_type": fb.get("feedback_type"),
            "phase": fb.get("phase"), "shown_at_ms": at,
            "has_region": bool(region), "region": region,
            "revision": {
                "started": bool(evt and ev.canonical(evt.get("type")) == ev.REVISION_START),
                "skipped": bool(evt and ev.canonical(evt.get("type")) == ev.REVISION_SKIPPED),
                # how long the child sat with the feedback before acting on it
                "latency_ms": ((evt.get("t_ms") or 0) - at) if evt else None,
                "linked": bool(evt and (evt.get("payload") or {}).get("feedback_id") == fid),
            },
            "before": before, "after": after,
        }
        if region:
            b, a = before.get("share_in_region"), after.get("share_in_region")
            # The headline contrast: more work inside the targeted region than
            # before? None when a share is undefined (no drawing in that window)
            # — "revised somewhere else" is 0.0 and must not look like
            # "revised nothing", which is not a compliance measurement at all.
            rec["region_shift"] = round(a - b, 4) if (a is not None and b is not None) else None
        out.append(rec)
    return {"session_id": d.name, "n_feedback": len(out), "feedback": out}
