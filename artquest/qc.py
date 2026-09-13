"""End-of-session data-quality checks.

Runs when a session finishes and writes its verdict into `metadata.json`, so a
bad run is visible at collection time rather than months later during analysis.
Nothing here deletes or rewrites data — a failed check is a flag, not a filter.
"""
import os
from typing import Any, Dict, List, Optional

MIN_DURATION_MS = 5_000          # anything shorter is almost certainly a misfire
MAX_DURATION_MS = 6 * 3600_000   # a browser tab left open overnight
MIN_STROKES = 1
MIN_POINTS_PER_STROKE = 2.0      # a stroke with a single point cannot be replayed
# Largest share of ink allowed to disagree between the artwork rebuilt from the
# logs and the PNG the child actually saved (`reconstruct.compare`'s `rel`).
#
# Calibrated on the browser-drawn sessions in `data/`: a *correct* replay still
# scores 0.11–0.13, because PIL draws a line thinner and harder-edged than the
# canvas does (replay ink runs ~78 % of the artwork's). 0.30 leaves a bit over
# 2x headroom above that floor while still catching gross divergence — a blank
# replay, the wrong canvas size, a lost batch of strokes.
#
# It is a net, not a proof: a couple of extra strokes in a busy drawing score
# well under it. The precise, threshold-free check is `log_streams_agree` below
# — that is the one to trust. Widen or tighten this once pilot data exists; the
# measured value always lands in the check's detail.
MAX_REPLAY_REL_DIFF = float(os.environ.get("ARTQUEST_MAX_REPLAY_DIFF", "0.30"))


def check(meta: Dict[str, Any], *, strokes: Dict[str, Any], events: int,
          known_task: bool, has_final_image: bool, pending_uploads: int = 0,
          replay: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        # The two checks that cannot be recovered later: if the logs disagree
        # with each other, or the drawing rebuilt from them is not the drawing
        # that was saved, nothing downstream can tell which one is right.
        {"name": "log_streams_agree",
         "ok": bool(replay) and (replay.get("streams") or {}).get("status") != "mismatch",
         "detail": (replay or {}).get("streams")},
        {"name": "replay_matches_final",
         "ok": bool(replay) and replay.get("rel") is not None and replay["rel"] <= MAX_REPLAY_REL_DIFF,
         "detail": {k: v for k, v in (replay or {}).items() if k != "streams"} or None},
    ]
    failed = [c["name"] for c in checks if not c["ok"]]
    counts = {"strokes": n_strokes, "points": n_points, "events": events, "duration_ms": duration}
    if replay:
        # strokes that were drawn and then undone or cleared away: a process
        # signal in its own right, not an error
        counts["strokes_visible"] = replay.get("strokes_visible")
        counts["strokes_removed"] = replay.get("strokes_removed")
    return {"ok": not failed, "failed": failed, "checks": checks, "counts": counts}
