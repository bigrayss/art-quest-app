"""Flatten the session directories into analysis-ready CSVs.

    python3 tools/export_dataset.py --out export/ [--points]

Writes sessions.csv, strokes.csv, events.csv, feedback.csv, questionnaire.csv —
and with --points, points.csv (one row per sampled pen point; large).

Nothing is aggregated beyond counts: stroke speed, hesitation and rhythm stay
where they belong, in the analysis scripts that read these files.
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artquest import config  # noqa: E402
from artquest.reconstruct import read_jsonl  # noqa: E402

SESSION_COLS = [
    "session_id", "created_at", "started_at", "ended_at", "duration_ms",
    "anon_id", "participant_id", "task_id", "task_category", "difficulty",
    "time_limit_sec", "allowed_tools", "reference_id", "order_index", "sequence_id",
    "study_active", "study_id", "group", "cond_ui", "cond_reference_allowed",
    "cond_undo_allowed", "cond_questionnaire", "cond_feedback_source",
    "emotion", "intent_text", "status", "revised",
    "n_strokes", "n_points", "n_events", "n_snapshots",
    "qc_ok", "qc_failed", "app_version", "schema_version", "canvas_w", "canvas_h", "device_platform",
]


def _flat_session(m: Dict[str, Any]) -> Dict[str, Any]:
    p, t, c = m.get("participant") or {}, m.get("task") or {}, m.get("condition") or {}
    st, times, counts = m.get("study") or {}, m.get("times") or {}, m.get("counts") or {}
    qc, intent, canvas = m.get("qc") or {}, m.get("intent") or {}, m.get("canvas") or {}
    if isinstance(p, str):  # schema 1
        p = {"participant_id": p, "anon_id": ""}
    return {
        "session_id": m.get("id"), "created_at": m.get("created_at"),
        "started_at": times.get("started_at"), "ended_at": times.get("ended_at"),
        "duration_ms": times.get("duration_ms"),
        "anon_id": p.get("anon_id", ""), "participant_id": p.get("participant_id", ""),
        "task_id": m.get("quest_id"), "task_category": t.get("category"), "difficulty": t.get("difficulty"),
        "time_limit_sec": t.get("time_limit_sec"),
        "allowed_tools": "|".join(t.get("allowed_tools") or []) if t.get("allowed_tools") else "",
        "reference_id": t.get("reference_id") or "", "order_index": t.get("order_index"),
        "sequence_id": t.get("sequence_id", ""),
        "study_active": st.get("active"), "study_id": st.get("study_id", ""), "group": st.get("group", ""),
        "cond_ui": c.get("ui"), "cond_reference_allowed": c.get("reference_allowed"),
        "cond_undo_allowed": c.get("undo_allowed"), "cond_questionnaire": c.get("questionnaire"),
        "cond_feedback_source": c.get("feedback_source"),
        "emotion": intent.get("emotion", ""), "intent_text": intent.get("text", ""),
        "status": m.get("status"), "revised": m.get("revised"),
        "n_strokes": counts.get("strokes", 0), "n_points": counts.get("points", 0),
        "n_events": counts.get("events", 0), "n_snapshots": counts.get("snapshots", 0),
        "qc_ok": qc.get("ok"), "qc_failed": "|".join(qc.get("failed") or []),
        "app_version": (m.get("app") or {}).get("version", ""), "schema_version": m.get("schema_version", 1),
        "canvas_w": canvas.get("width"), "canvas_h": canvas.get("height"),
        "device_platform": (m.get("device") or {}).get("platform", ""),
    }


def _write(path: Path, cols: List[str], rows: List[Dict[str, Any]]) -> int:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def export(out: Path, with_points: bool = False) -> Dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    sessions, strokes, events, feedback, quest = [], [], [], [], []
    points_path = out / "points.csv"
    pf = points_path.open("w", newline="", encoding="utf-8") if with_points else None
    pw = csv.writer(pf) if pf else None
    if pw:
        pw.writerow(["session_id", "stroke_id", "i", "x", "y", "t_ms", "pressure", "tilt_x", "tilt_y"])

    for d in sorted(config.SESSIONS_DIR.iterdir()):
        meta_p = d / "metadata.json"
        if not meta_p.exists():
            continue
        m = json.loads(meta_p.read_text(encoding="utf-8"))
        sid = m.get("id") or d.name
        sessions.append(_flat_session(m))

        for s in read_jsonl(d / "strokes.jsonl"):
            pts = s.get("points") or []
            strokes.append({
                "session_id": sid, "stroke_id": s.get("stroke_id"), "seq": s.get("seq"), "phase": s.get("phase"),
                "t_start_ms": s.get("t_start_ms"), "t_end_ms": s.get("t_end_ms"),
                "duration_ms": (s.get("t_end_ms") or 0) - (s.get("t_start_ms") or 0),
                "tool": s.get("tool"), "color": s.get("color"), "size": s.get("size"),
                "opacity": s.get("opacity"), "erase": s.get("erase"), "pointer_type": s.get("pointer_type"),
                "zoom": s.get("zoom", 1.0),   # what the child could see while drawing it
                "n_points": len(pts),
                "mean_pressure": round(sum((p[3] if len(p) > 3 else 0) for p in pts) / len(pts), 4) if pts else "",
            })
            if pw:
                for i, p in enumerate(pts):
                    p = list(p) + [""] * (6 - len(p))
                    pw.writerow([sid, s.get("stroke_id"), i, p[0], p[1],
                                 (s.get("t_start_ms") or 0) + (p[2] or 0), p[3], p[4], p[5]])

        for e in read_jsonl(d / "events.jsonl"):
            events.append({"session_id": sid, "seq": e.get("seq"), "src": e.get("src"), "ts": e.get("ts"),
                           "t_ms": e.get("t_ms"), "type": e.get("type"),
                           "payload": json.dumps(e.get("payload"), ensure_ascii=False) if e.get("payload") else ""})
        for f in read_jsonl(d / "feedback.jsonl"):
            feedback.append({"session_id": sid, **{k: f.get(k) for k in
                             ("feedback_id", "t_ms", "phase", "source", "feedback_type", "backend", "text", "shown_at")},
                             "target_region": json.dumps(f.get("target_region"), ensure_ascii=False) if f.get("target_region") else ""})
        q = d / "questionnaire.json"
        if q.exists():
            quest.append({"session_id": sid, **json.loads(q.read_text(encoding="utf-8"))})

    if pf:
        pf.close()
    counts = {
        "sessions": _write(out / "sessions.csv", SESSION_COLS, sessions),
        "strokes": _write(out / "strokes.csv", ["session_id", "stroke_id", "seq", "phase", "t_start_ms", "t_end_ms",
                                                "duration_ms", "tool", "color", "size", "opacity", "erase",
                                                "pointer_type", "zoom", "n_points", "mean_pressure"], strokes),
        "events": _write(out / "events.csv", ["session_id", "seq", "src", "ts", "t_ms", "type", "payload"], events),
        "feedback": _write(out / "feedback.csv", ["session_id", "feedback_id", "t_ms", "phase", "source",
                                                  "feedback_type", "backend", "text", "target_region", "shown_at"], feedback),
        "questionnaire": _write(out / "questionnaire.csv", ["session_id", "difficulty", "confidence", "enjoyment",
                                                            "hardest_part", "free_text", "at"], quest),
    }
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("export"))
    ap.add_argument("--points", action="store_true", help="also write points.csv (one row per sampled point)")
    a = ap.parse_args()
    counts = export(a.out, a.points)
    for k, v in counts.items():
        print(f"{k:14s} {v}")
    print(f"→ {a.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
