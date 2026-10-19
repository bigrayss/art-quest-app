"""End-of-session data-quality checks.

Runs when a session finishes and writes its verdict into `metadata.json`, so a
bad run is visible at collection time rather than months later during analysis.
Nothing here deletes or rewrites data — a failed check is a flag, not a filter.
"""
import os
from typing import Any, Dict, List, Optional

from .events import SESSION_END, SESSION_START, SYNC_MARK, canonical, client_clock_anchor

MIN_DURATION_MS = 5_000          # anything shorter is almost certainly a misfire
MAX_DURATION_MS = 6 * 3600_000   # a browser tab left open overnight
MIN_STROKES = 1
MAX_STROKES = 5_000        # far past any plausible drawing; a runaway logger
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
          replay: Optional[Dict[str, Any]] = None,
          condition_frozen: bool = True, reference_available: Optional[bool] = None,
          checksum: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    # An abandoned session is intentionally incomplete. Running the full battery
    # on it would bury real failures under noise nobody will ever act on.
    if meta.get("status") == "abandoned":
        return {"ok": True, "failed": [], "abandoned": True,
                "checks": [{"name": "abandoned", "ok": True,
                            "detail": meta.get("abandoned_reason")}],
                "counts": {"strokes": strokes.get("count", 0), "events": events}}
    times = meta.get("times") or {}
    duration = times.get("duration_ms") or 0
    n_strokes, n_points = strokes.get("count", 0), strokes.get("points", 0)
    ppl = (n_points / n_strokes) if n_strokes else 0.0

    checks: List[Dict[str, Any]] = [
        {"name": "task_known", "ok": known_task, "detail": meta.get("quest_id")},
        # without the frozen definition, a task_id alone cannot recover what the
        # child was actually shown once the library moves on
        {"name": "condition_frozen", "ok": condition_frozen,
         "detail": (meta.get("task") or {}).get("task_version")},
        # not a failure of the session, a warning about the stimulus it used
        {"name": "stimulus_ready", "ok": not (meta.get("task") or {}).get("stimulus_placeholder"),
         "detail": (meta.get("task") or {}).get("stimulus_id")},
        {"name": "events_nonempty", "ok": events > 0, "detail": events},
        {"name": "strokes_nonempty", "ok": n_strokes >= MIN_STROKES, "detail": n_strokes},
        {"name": "stroke_count_plausible", "ok": n_strokes <= MAX_STROKES, "detail": n_strokes},
        {"name": "canvas_recorded",
         "ok": bool((meta.get("canvas") or {}).get("width")) and bool((meta.get("canvas") or {}).get("height")),
         "detail": meta.get("canvas")},
        # a reference task whose stimulus never loaded measured something else
        {"name": "reference_available", "ok": reference_available is not False,
         "detail": (meta.get("task") or {}).get("reference_id")},
        {"name": "log_checksum", "ok": bool(checksum), "detail": checksum},
        # strokes were logged but the artwork is empty: everything was erased,
        # or the export went wrong. Either way analysis needs to know.
        {"name": "artwork_nonblank",
         "ok": not (n_strokes > 0 and (replay or {}).get("final_ink") == 0),
         "detail": (replay or {}).get("final_ink")},
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


def check_paper(meta: Dict[str, Any], *, events: List[Dict[str, Any]], artifacts: List[Dict[str, Any]],
                n_strokes: int, known_task: bool, pending_uploads: int = 0, condition_frozen: bool = True,
                reference_available: Optional[bool] = None,
                checksum: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """纸面 session（condition.medium = paper）的那一组检查。

    画在纸上，屏上本来就是 0 笔，所以笔画、回放、画布这几项全不适用——查它们只会让每个纸面
    session 都「失败」，真问题反而被埋掉。换成三件事：有终稿图（而且字节和记下的 hash 对得上）、
    有开始和结束、有同步标记（对得上外面的钟）。`artifacts` 是 session.json 里那份记录，
    每条另带 `file_ok` / `hash_ok`（盘上那份还在不在、hash 对不对，由调用方现算）。
    """
    if meta.get("status") == "abandoned":
        return {"ok": True, "failed": [], "abandoned": True, "medium": "paper",
                "checks": [{"name": "abandoned", "ok": True, "detail": meta.get("abandoned_reason")}],
                "counts": {"strokes": n_strokes, "events": len(events)}}
    times = meta.get("times") or {}
    duration = times.get("duration_ms") or 0
    types = {canonical(e.get("type", "")) for e in events}
    anchor = client_clock_anchor(events)
    visible = [(e.get("payload") or {}).get("source") for e in events
               if canonical(e.get("type", "")) == SYNC_MARK and (e.get("payload") or {}).get("visible")]
    # 开了看得见的标记，开始和结束那两下必须都在：相机靠它们把这一段对上
    need = ["start", "submit"] if (meta.get("condition") or {}).get("sync_marks") else []
    finals = [a for a in artifacts if a.get("kind") == "final" and not a.get("superseded_by")]
    bad = [a.get("artifact_id") for a in artifacts if not (a.get("file_ok") and a.get("hash_ok"))]
    checks: List[Dict[str, Any]] = [
        {"name": "task_known", "ok": known_task, "detail": meta.get("quest_id")},
        {"name": "condition_frozen", "ok": condition_frozen,
         "detail": (meta.get("task") or {}).get("task_version")},
        {"name": "stimulus_ready", "ok": not (meta.get("task") or {}).get("stimulus_placeholder"),
         "detail": (meta.get("task") or {}).get("stimulus_id")},
        {"name": "events_nonempty", "ok": bool(events), "detail": len(events)},
        # 屏上有笔画，说明条件写的是纸、人却在屏上画：两份记录互相矛盾
        {"name": "no_canvas_strokes", "ok": n_strokes == 0, "detail": n_strokes},
        {"name": "reference_available", "ok": reference_available is not False,
         "detail": (meta.get("task") or {}).get("reference_id")},
        {"name": "log_checksum", "ok": bool(checksum), "detail": checksum},
        {"name": "final_artwork_uploaded", "ok": bool(finals) and bool(finals[-1].get("file_ok")),
         "detail": finals[-1].get("artifact_id") if finals else None},
        {"name": "artifacts_intact", "ok": not bad, "detail": bad or len(artifacts)},
        {"name": "session_started", "ok": bool(times.get("started_at")) and SESSION_START in types,
         "detail": times.get("started_at")},
        {"name": "session_ended", "ok": bool(times.get("ended_at")) and SESSION_END in types,
         "detail": times.get("ended_at")},
        {"name": "times_monotonic",
         "ok": bool(times.get("created_at")) and (not times.get("ended_at") or times.get("ended_at") >= times.get("created_at")),
         "detail": {"created_at": times.get("created_at"), "ended_at": times.get("ended_at")}},
        {"name": "duration_plausible", "ok": MIN_DURATION_MS <= duration <= MAX_DURATION_MS, "detail": duration},
        {"name": "sync_marks_present", "ok": anchor is not None and all(s in visible for s in need),
         "detail": {"anchor": anchor is not None, "visible": len(visible), "sources": sorted(set(visible)),
                    "required": need}},
        {"name": "uploads_flushed", "ok": pending_uploads == 0, "detail": pending_uploads},
    ]
    failed = [c["name"] for c in checks if not c["ok"]]
    counts = {"strokes": n_strokes, "events": len(events), "duration_ms": duration,
              "artifacts_final": sum(1 for a in artifacts if a.get("kind") == "final"),
              "artifacts_stage": sum(1 for a in artifacts if a.get("kind") == "stage"),
              "sync_marks_visible": len(visible)}
    return {"ok": not failed, "failed": failed, "checks": checks, "counts": counts, "medium": "paper"}
