"""End-of-session data-quality checks.

Runs when a session finishes and writes its verdict into `metadata.json`, so a
bad run is visible at collection time rather than months later during analysis.
Nothing here deletes or rewrites data — a failed check is a flag, not a filter.
"""
from typing import Any, Dict, List

MIN_DURATION_MS = 5_000          # anything shorter is almost certainly a misfire
MAX_DURATION_MS = 6 * 3600_000   # a browser tab left open overnight
MIN_STROKES = 1
MIN_POINTS_PER_STROKE = 2.0      # a stroke with a single point cannot be replayed


def check(meta: Dict[str, Any], *, strokes: Dict[str, Any], events: int,
          known_task: bool, has_final_image: bool, pending_uploads: int = 0) -> Dict[str, Any]:
    times = meta.get("times") or {}
    duration = times.get("duration_ms") or 0
    n_strokes, n_points = strokes.get("count", 0), strokes.get("points", 0)
    ppl = (n_points / n_strokes) if n_strokes else 0.0

    checks: List[Dict[str, Any]] = [
        {"name": "task_known", "ok": known_task, "detail": meta.get("quest_id")},
        {"name": "events_nonempty", "ok": events > 0, "detail": events},
        {"name": "strokes_nonempty", "ok": n_strokes >= MIN_STROKES, "detail": n_strokes},
        {"name": "final_image_saved", "ok": has_final_image, "detail": None},
        {"name": "times_monotonic",
         "ok": bool(times.get("created_at")) and (not times.get("ended_at") or times.get("ended_at") >= times.get("created_at")),
         "detail": {"created_at": times.get("created_at"), "ended_at": times.get("ended_at")}},
        {"name": "duration_plausible", "ok": MIN_DURATION_MS <= duration <= MAX_DURATION_MS, "detail": duration},
        {"name": "strokes_replayable", "ok": ppl >= MIN_POINTS_PER_STROKE, "detail": round(ppl, 2)},
        {"name": "uploads_flushed", "ok": pending_uploads == 0, "detail": pending_uploads},
    ]
    failed = [c["name"] for c in checks if not c["ok"]]
    return {"ok": not failed, "failed": failed, "checks": checks,
            "counts": {"strokes": n_strokes, "points": n_points, "events": events, "duration_ms": duration}}
