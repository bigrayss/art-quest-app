"""Flatten the session directories into analysis-ready CSVs.

    python3 tools/export_dataset.py --out export/ [--points]

Writes sessions.csv, strokes.csv, events.csv, feedback.csv, questionnaire.csv, calls.csv (+ prompts/), assist_clicks.csv —
and with --points, points.csv (one row per sampled pen point; large).

Nothing is aggregated beyond counts: stroke speed, hesitation and rhythm stay
where they belong, in the analysis scripts that read these files.
"""
import argparse
import csv
import shutil
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artquest import config  # noqa: E402
from artquest import events as ev  # noqa: E402
from artquest.logstore import write_json  # noqa: E402
from artquest.storage import (dataset_manifest, session_events, session_feedback,  # noqa: E402
                              session_labels, session_meta, session_part, session_calls, calls_recorded, prompts_dir, session_strokes, sid_of)
from artquest.revision import attribute  # noqa: E402
from artquest.quests import QUESTS  # noqa: E402
from artquest.scoring.base import DIM_KEYS  # noqa: E402

TASK_COLS = ["task_id", "family", "mission_family", "form_id", "version", "prompt_style",
             "title", "instruction", "category", "difficulty", "time_limit_sec",
             "allowed_tools", "stimulus_kind", "stimulus_id", "stimulus_placeholder",
             "primary_dims", "secondary_dims", "exploratory_dims", "na_dims",
             "process_targets", "research_goal"]


def _mean_pressure(points):
    vals = [p[3] for p in points if len(p) > 3 and isinstance(p[3], (int, float))]
    return round(sum(vals) / len(vals), 4) if vals else ""


def _flat_task(t):
    r = t.get("rubric") or {}
    return {"task_id": t["task_id"], "family": t.get("family", ""),
            "mission_family": t.get("family_slug", ""), "form_id": t.get("form_id", ""),
            "version": t.get("version", ""), "prompt_style": t.get("prompt_style", ""),
            "title": t.get("title", ""), "instruction": t.get("instruction", ""),
            "category": t.get("category", ""), "difficulty": t.get("difficulty"),
            "time_limit_sec": t.get("time_limit_sec"),
            "allowed_tools": "|".join(t.get("allowed_tools") or []),
            "stimulus_kind": (t.get("stimulus") or {}).get("kind", "none"),
            "stimulus_id": t.get("stimulus_id", ""),
            "stimulus_placeholder": bool(t.get("stimulus_placeholder")),
            "primary_dims": "|".join(r.get("primary_dimensions") or []),
            "secondary_dims": "|".join(r.get("secondary_dimensions") or []),
            "exploratory_dims": "|".join(r.get("exploratory_dimensions") or []),
            "na_dims": "|".join(r.get("not_applicable_dimensions") or []),
            "process_targets": "|".join(t.get("process_targets") or []),
            "research_goal": t.get("research_goal", "")}

SESSION_COLS = [
    "session_id", "created_at", "started_at", "ended_at", "duration_ms",
    "anon_id", "participant_id", "task_id", "task_category", "difficulty",
    "family", "mission_family", "form_id", "prompt_style", "task_version",
    "stimulus_id", "stimulus_kind", "stimulus_placeholder",
    "primary_dims", "secondary_dims", "na_dims",
    "time_limit_sec", "allowed_tools", "reference_id", "order_index", "sequence_id",
    "study_active", "study_id", "group", "cond_ui", "cond_reference_allowed",
    "cond_undo_allowed", "cond_questionnaire", "cond_feedback_source",
    "cond_zoom_allowed", "cond_history_mode",
    "emotion", "intent_text", "status", "revised",
    # 首访任务库（2026-10-12）：按年龄路由的记录 + 任务实例的几项条件（年龄是协变量，不是能力分数）
    "bank", "band", "routing_age", "routing_age_source", "first_visit", "revision_enabled", "reference_fit", "post_config",
    "n_strokes", "n_points", "n_events", "n_snapshots",
    "qc_ok", "qc_failed", "app_version", "schema_version", "canvas_w", "canvas_h", "device_platform",
    "calls_recorded", "n_calls",
]


# One row per session: the personalisation arm, what it predicted before the
# child drew, and what the child then reported. This is the table the
# No History / User History / Personalized Model comparison is read off.
PERSONALIZATION_COLS = [
    "session_id", "participant_id", "task_id", "task_difficulty",
    "requested_mode", "backend", "available", "cold_start", "n_prior_tasks",
    "pred_difficulty", "pred_confidence", "actual_difficulty", "actual_confidence",
    "err_difficulty", "err_confidence", "abs_err_difficulty", "abs_err_confidence",
    "weakest_dims", "basis", "n_shown", "builder", "frozen_at",
]


def _flat_personalization(m: Dict[str, Any], rec: Dict[str, Any]) -> Dict[str, Any]:
    p = m.get("participant") or {}
    if isinstance(p, str):
        p = {"participant_id": p}
    used, pred = rec.get("history_used") or {}, rec.get("prediction") or {}
    out = rec.get("outcome") or {}
    err = rec.get("error") or {}
    row = {
        "session_id": sid_of(m), "participant_id": p.get("participant_id", ""),
        "task_id": m.get("quest_id"), "task_difficulty": (m.get("task") or {}).get("difficulty"),
        "requested_mode": rec.get("requested_mode"), "backend": rec.get("backend"),
        "available": rec.get("available"), "cold_start": used.get("cold_start"),
        "n_prior_tasks": used.get("n_tasks"),
        "weakest_dims": "|".join(pred.get("weakest_dims") or []),
        "basis": pred.get("basis", ""), "n_shown": len(rec.get("shown") or []),
        "builder": used.get("builder") or "", "frozen_at": rec.get("frozen_at", ""),
    }
    for key in ("difficulty", "confidence"):
        row[f"pred_{key}"] = pred.get(key)
        row[f"actual_{key}"] = out.get(key)
        row[f"err_{key}"] = err.get(key)
        row[f"abs_err_{key}"] = abs(err[key]) if isinstance(err.get(key), (int, float)) else ""
    return row


def _flat_session(m: Dict[str, Any]) -> Dict[str, Any]:
    p, t, c = m.get("participant") or {}, m.get("task") or {}, m.get("condition") or {}
    st, times, counts = m.get("study") or {}, m.get("times") or {}, m.get("counts") or {}
    qc, intent, canvas = m.get("qc") or {}, m.get("intent") or {}, m.get("canvas") or {}
    if isinstance(p, str):  # schema 1
        p = {"participant_id": p, "anon_id": ""}
    return {
        "session_id": sid_of(m), "created_at": m.get("created_at"),
        "started_at": times.get("started_at"), "ended_at": times.get("ended_at"),
        "duration_ms": times.get("duration_ms"),
        "anon_id": p.get("anon_id", ""), "participant_id": p.get("participant_id", ""),
        "task_id": m.get("quest_id"), "task_category": t.get("category"), "difficulty": t.get("difficulty"),
        "family": t.get("family", ""), "mission_family": t.get("mission_family", ""),
        "form_id": t.get("form_id", ""), "prompt_style": t.get("prompt_style", ""),
        "task_version": t.get("task_version", ""),
        "stimulus_id": t.get("stimulus_id", ""), "stimulus_kind": t.get("stimulus_kind", ""),
        "stimulus_placeholder": t.get("stimulus_placeholder"),
        # the rubric contract travels with the row: a reader must be able to tell
        # a dimension this task could not test from one it tested badly
        "primary_dims": "|".join((t.get("rubric") or {}).get("primary_dimensions") or []),
        "secondary_dims": "|".join((t.get("rubric") or {}).get("secondary_dimensions") or []),
        "na_dims": "|".join((t.get("rubric") or {}).get("not_applicable_dimensions") or []),
        "time_limit_sec": t.get("time_limit_sec"),
        "allowed_tools": "|".join(t.get("allowed_tools") or []) if t.get("allowed_tools") else "",
        "reference_id": t.get("reference_id") or "", "order_index": t.get("order_index"),
        "sequence_id": t.get("sequence_id", ""),
        "study_active": st.get("active"), "study_id": st.get("study_id", ""), "group": st.get("group", ""),
        "cond_ui": c.get("ui"), "cond_reference_allowed": c.get("reference_allowed"),
        "cond_undo_allowed": c.get("undo_allowed"), "cond_questionnaire": c.get("questionnaire"),
        "cond_feedback_source": c.get("feedback_source"),
        "cond_zoom_allowed": c.get("zoom_allowed"), "cond_history_mode": c.get("history_mode"),
        "emotion": intent.get("emotion", ""), "intent_text": intent.get("text", ""),
        "status": m.get("status"), "revised": m.get("revised"),
        "bank": t.get("bank", ""), "band": t.get("band", "") or (m.get("routing") or {}).get("band", ""),
        "routing_age": (m.get("routing") or {}).get("age"), "routing_age_source": (m.get("routing") or {}).get("age_source", ""),
        "first_visit": (m.get("routing") or {}).get("first_visit"),
        "revision_enabled": (t.get("task_condition") or {}).get("revision_enabled"),
        "reference_fit": (t.get("task_condition") or {}).get("reference_fit", ""),
        "post_config": t.get("post_config", ""),
        "n_strokes": counts.get("strokes", 0), "n_points": counts.get("points", 0),
        "n_events": counts.get("events", 0), "n_snapshots": counts.get("snapshots", 0),
        "qc_ok": qc.get("ok"), "qc_failed": "|".join(qc.get("failed") or []),
        "app_version": (m.get("app") or {}).get("version", ""), "schema_version": m.get("schema_version", 1),
        "canvas_w": canvas.get("width"), "canvas_h": canvas.get("height"),
        "device_platform": (m.get("device") or {}).get("platform", ""),
    }


CALL_COLS = ["session_id", "call_id", "group_id", "operation_id", "attempt", "purpose", "stage", "dimension_id",
             "execution_kind", "provider", "backend", "model", "prompt_version", "system_hash", "started_at",
             "seconds", "outcome", "http_status", "error", "prompt_tokens", "completion_tokens", "n_images",
             "image_files", "image_sha256", "input_chars", "input_text", "output_text", "finish_reason",
             "reasoning_chars", "provider_request_id", "key_index"]


def _flat_call(sid: str, c: Dict[str, Any]) -> Dict[str, Any]:
    """calls.jsonl 一行 → 一行 CSV。输入文字拼起来放一列（local 记录的 input 是结构体，就整个 JSON 化）。"""
    inp = c.get("input") or {}
    out = c.get("output") or {}
    usage = c.get("usage") or {}
    texts = inp.get("text")
    input_text = "\n".join(texts) if isinstance(texts, list) else json.dumps(inp, ensure_ascii=False)
    images = inp.get("images") or []
    return {
        **{k: c.get(k) for k in ("call_id", "group_id", "operation_id", "attempt", "purpose", "stage", "dimension_id",
                                 "execution_kind", "provider", "backend", "model", "prompt_version", "system_hash",
                                 "started_at", "seconds", "outcome", "http_status", "error", "provider_request_id",
                                 "key_index")},
        "session_id": sid,
        "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
        "n_images": len(images), "image_files": "|".join(str(i.get("file") or "") for i in images),
        "image_sha256": "|".join(str(i.get("sha256") or "") for i in images),
        "input_chars": len(input_text), "input_text": input_text,
        "output_text": out.get("text") if isinstance(out, dict) and "text" in out else json.dumps(out, ensure_ascii=False),
        "finish_reason": out.get("finish_reason") if isinstance(out, dict) else None,
        "reasoning_chars": out.get("reasoning_chars") if isinstance(out, dict) else None,
    }


ASSIST_CLICK_COLS = ["session_id", "click_id", "nth", "t_ms", "phase", "cached", "offline", "deferred",
                     "n_strokes_client", "n_strokes_server", "server_count_at", "frame_file", "frame_sha256",
                     "frame_bytes", "call_id", "group_id", "source_call_id", "backend", "text", "received_at"]


def _flat_click(sid: str, c: Dict[str, Any]) -> Dict[str, Any]:
    f = c.get("frame") or {}
    return {**{k: c.get(k) for k in ASSIST_CLICK_COLS if k not in ("session_id", "frame_file", "frame_sha256", "frame_bytes")},
            "session_id": sid, "frame_file": f.get("file"), "frame_sha256": f.get("sha256"), "frame_bytes": f.get("bytes")}


DECISION_COLS = ["session_id", "decision_id", "offer_id", "authority", "decision_status", "entrypoint", "choice_source",
                 "source", "offline", "chosen_task_id", "in_offered", "rules_version", "task_version", "bank_version",
                 "rule", "identity_key", "history_revision", "n_done", "done_task_ids", "age", "age_source", "band",
                 "n_candidates", "n_offered", "offered", "client_offered", "same_set", "same_order", "prepared_at",
                 "consumed_by", "ticket"]


def _flat_decision(sid: str, dec: Dict[str, Any], selection: Dict[str, Any], ticket_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    h, r = dec.get("history") or {}, dec.get("routing") or {}
    offered = [o.get("task_id") or o.get("family") or "" for o in (dec.get("offered") or [])]
    # 对照结果在 offer 上：session 里拷了 offers；未消费的票上直接有 offers
    offers = selection.get("offers") if selection else None
    if offers is None and ticket_meta is not None:
        offers = [o for o in (ticket_meta.get("offers") or []) if o.get("decision_id") == dec.get("decision_id")]
    want = (selection or {}).get("offer_id")
    offer = next((o for o in (offers or []) if o.get("offer_id") == want), (offers or [None])[-1] if offers else None) or {}
    match = offer.get("match") or {}
    return {
        "session_id": sid, "decision_id": dec.get("decision_id") or (selection or {}).get("decision_id"),
        "offer_id": (selection or {}).get("offer_id") or offer.get("offer_id"),
        "authority": (selection or {}).get("authority") or dec.get("authority"),
        "decision_status": (selection or {}).get("decision_status"), "entrypoint": (selection or {}).get("entrypoint") or dec.get("entrypoint"),
        "choice_source": (selection or {}).get("choice_source"), "source": (selection or {}).get("source"),
        "offline": (selection or {}).get("offline"), "chosen_task_id": (selection or {}).get("chosen_task_id"),
        "in_offered": (selection or {}).get("in_offered"), "rules_version": dec.get("rules_version"),
        "task_version": dec.get("task_version"), "bank_version": dec.get("bank_version"), "rule": dec.get("rule"),
        "identity_key": dec.get("identity_key"), "history_revision": dec.get("prepared_at"),
        "n_done": h.get("n_done"), "done_task_ids": "|".join(h.get("done_task_ids") or []),
        "age": r.get("age"), "age_source": r.get("age_source"), "band": r.get("band"),
        "n_candidates": len(dec.get("candidates") or []), "n_offered": len(offered), "offered": "|".join(offered),
        "client_offered": "|".join((selection or {}).get("client_offered") or offer.get("client_offered") or []),
        "same_set": match.get("same_set"), "same_order": match.get("same_order"),
        "prepared_at": dec.get("prepared_at"), "consumed_by": dec.get("consumed_by"), "ticket": dec.get("ticket"),
    }


def _write(path: Path, cols: List[str], rows: List[Dict[str, Any]]) -> int:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def export(out: Path, with_points: bool = False) -> Dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    sessions, strokes, events, feedback, quest, personal, ratings = [], [], [], [], [], [], []
    annotations, calls, clicks, decisions, unconsumed = [], [], [], [], []
    points_path = out / "points.csv"
    pf = points_path.open("w", newline="", encoding="utf-8") if with_points else None
    pw = csv.writer(pf) if pf else None
    if pw:
        pw.writerow(["session_id", "stroke_id", "i", "x", "y", "t_ms", "pressure", "tilt_x", "tilt_y"])

    for d in sorted(config.SESSIONS_DIR.iterdir()):
        m = session_meta(d)
        if not m:
            continue
        if m.get("lifecycle") in ("issued", "prepared"):
            # 没花掉的票不是作品：没有画、没有时间、没有任务。prepared 是服务端的决策票：
            # 没被消费的决策另出一张表（decisions_unconsumed.csv），不混进作品样本
            if m.get("lifecycle") == "prepared":
                for dec in [m.get("decision")] + list(m.get("superseded") or []):
                    if dec and not dec.get("consumed_by"):
                        unconsumed.append(_flat_decision("", dec, {"decision_status": "unconsumed"}, m))
            continue
        sid = sid_of(m) or d.name
        row = _flat_session(m)
        # 「没采集」和「零次」要分得开：schema 4 之前的 session 没有 calls.jsonl
        cs = session_calls(d) if calls_recorded(d) else None
        row["calls_recorded"] = cs is not None
        row["n_calls"] = len(cs) if cs is not None else None
        sessions.append(row)
        pz = session_part(d, "personalization")
        if pz:
            personal.append(_flat_personalization(m, pz))
        # schema 4 起每次模型/引擎执行一条；文件不在 = 没采集（sessions.csv 的 calls_recorded 说得清），不是零次
        if cs:
            calls.extend(_flat_call(sid, c) for c in cs)
        clicks.extend(_flat_click(sid, c) for c in (m.get("assist_clicks") or []))
        if m.get("selection"):
            decisions.append(_flat_decision(sid, (m["selection"].get("decision") or {}), m["selection"], None))

        for s in session_strokes(d):
            pts = s.get("points") or []
            t0, t1 = ev.stroke_start_ms(s), ev.stroke_end_ms(s)
            strokes.append({
                "session_id": sid, "stroke_id": s.get("stroke_id"), "seq": s.get("seq"), "phase": s.get("phase"),
                "t0_ms": t0, "t_end_ms": t1, "duration_ms": t1 - t0,
                "tool": s.get("tool"), "color": s.get("color"), "size": s.get("size"),
                "opacity": s.get("opacity"), "op": s.get("op"), "pointer": s.get("pointer"),
                "zoom": s.get("zoom", 1.0),   # what the child could see while drawing it
                "n_points": len(pts),
                "pressure_supported": s.get("pressure_supported"),
                # only over points that actually measured it; blank when the
                # device never did, rather than a mean of fabricated values
                "mean_pressure": _mean_pressure(pts),
            })
            if pw:
                for i, p in enumerate(pts):
                    p = list(p) + [""] * (6 - len(p))
                    pw.writerow([sid, s.get("stroke_id"), i, p[0], p[1], t0 + (p[2] or 0), p[3], p[4], p[5]])

        for e in session_events(d):
            events.append({"session_id": sid, "seq": e.get("seq"), "src": e.get("src"),
                           "t_ms": e.get("t_ms"), "type": e.get("type"),
                           "payload": json.dumps(e.get("payload"), ensure_ascii=False) if e.get("payload") else ""})
        # one row per feedback, carrying what the child did after seeing it:
        # this is the unit of analysis for the feedback experiments
        attributed = {r["feedback_id"]: r for r in attribute(d)["feedback"] if r.get("feedback_id")}
        for f in session_feedback(d):
            a = attributed.get(f.get("feedback_id")) or {}
            rev, before, after = a.get("revision") or {}, a.get("before") or {}, a.get("after") or {}
            feedback.append({"session_id": sid, **{k: f.get(k) for k in
                             ("feedback_id", "t_ms", "phase", "source", "feedback_type", "backend", "text", "shown_at")},
                             "target_region": json.dumps(f.get("target_region"), ensure_ascii=False) if f.get("target_region") else "",
                             "trigger": f.get("trigger", ""), "model": f.get("model", ""),
                             "prompt_version": f.get("prompt_version", ""),
                             "has_region": a.get("has_region"),
                             "revision_started": rev.get("started"), "revision_skipped": rev.get("skipped"),
                             "revision_linked": rev.get("linked"), "latency_ms": rev.get("latency_ms"),
                             "strokes_before": before.get("strokes"), "strokes_after": after.get("strokes"),
                             "share_in_region_before": before.get("share_in_region"),
                             "share_in_region_after": after.get("share_in_region"),
                             "region_shift": a.get("region_shift")})

        for a in session_labels(d, "process_annotation"):
            annotations.append({"session_id": sid, "annotation_id": a.get("annotation_id"),
                                "rater_id": a.get("rater_id"), "label": a.get("label"),
                                "t_start_ms": a.get("t_start_ms"), "t_end_ms": a.get("t_end_ms"),
                                "duration_ms": (a.get("t_end_ms") or 0) - (a.get("t_start_ms") or 0),
                                "confidence": a.get("confidence"), "note": a.get("note", ""),
                                "ts": a.get("ts")})

        for r in session_labels(d, "rating"):
            ratings.append({"session_id": sid, "rating_id": r.get("rating_id"),
                            "source": r.get("source"), "rater_id": r.get("rater_id"),
                            "phase": r.get("phase"), "overall": r.get("overall"),
                            "note": r.get("note", ""), "ts": r.get("ts"),
                            **{f"dim_{k}": v for k, v in (r.get("dims") or {}).items()}})
        q = session_part(d, "self_report")
        if q:
            q = dict(q)
            if isinstance(q.get("skipped"), list):      # 首访问卷：跳过了哪几题，CSV 里用 | 连
                q["skipped"] = "|".join(q["skipped"])
            quest.append({"session_id": sid, **q})

    if pf:
        pf.close()
    # refresh the dataset-level manifest, next to the data and next to the export
    manifest = dataset_manifest()
    write_json(config.DATA_DIR / "dataset.json", manifest)
    write_json(out / "dataset.json", manifest)
    counts = {
        "sessions": _write(out / "sessions.csv", SESSION_COLS, sessions),
        "strokes": _write(out / "strokes.csv", ["session_id", "stroke_id", "seq", "phase", "t0_ms", "t_end_ms",
                                                "duration_ms", "tool", "color", "size", "opacity", "op",
                                                "pointer", "pressure_supported", "zoom",
                                                "n_points", "mean_pressure"], strokes),
        "events": _write(out / "events.csv", ["session_id", "seq", "src", "t_ms", "type", "payload"], events),
        "feedback": _write(out / "feedback.csv", ["session_id", "feedback_id", "t_ms", "phase", "source",
                                                  "feedback_type", "backend", "trigger", "model",
                                                  "prompt_version", "text", "target_region", "shown_at",
                                                  "has_region", "revision_started", "revision_skipped",
                                                  "revision_linked", "latency_ms", "strokes_before", "strokes_after",
                                                  "share_in_region_before", "share_in_region_after",
                                                  "region_shift"], feedback),
        "ratings": _write(out / "ratings.csv", ["session_id", "rating_id", "source", "rater_id", "phase",
                                                "overall"] + [f"dim_{k}" for k in DIM_KEYS] + ["note", "ts"], ratings),
        "questionnaire": _write(out / "questionnaire.csv", ["session_id", "difficulty", "confidence", "enjoyment",
                                                            "hardest_part_choice", "hardest_part",
                                                            "free_text", "reflection", "instrument", "skipped", "at"], quest),
        "annotations": _write(out / "annotations.csv", ["session_id", "annotation_id", "rater_id", "label",
                                                        "t_start_ms", "t_end_ms", "duration_ms",
                                                        "confidence", "note", "ts"], annotations),
        "personalization": _write(out / "personalization.csv", PERSONALIZATION_COLS, personal),
        "calls": _write(out / "calls.csv", CALL_COLS, calls),
        "assist_clicks": _write(out / "assist_clicks.csv", ASSIST_CLICK_COLS, clicks),
        # 一次任务安排三层：冻结候选 / 实际展示 / 实际选择。每条 session 一行（它选的那次），
        # 没被消费的服务端决策单独一张表——它们不是作品，不能混进样本
        "decisions": _write(out / "decisions.csv", DECISION_COLS, decisions),
        "decisions_unconsumed": _write(out / "decisions_unconsumed.csv", DECISION_COLS, unconsumed),
        # calls.csv 里的 system_hash 指向这些正文：固定提示词按 hash 归档一份，跟着数据走，不靠将来还能翻仓库
        "prompts": _copy_prompts(out / "prompts"),
        # the dataset ships its own measurement objects: without the task
        # definitions the session rows are ids nobody can resolve
        "tasks": _write(out / "tasks.csv", TASK_COLS, [_flat_task(t) for t in QUESTS]),
    }
    return counts


def _copy_prompts(dest: Path) -> int:
    src = prompts_dir()
    if not src.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.glob("*.txt")):
        shutil.copyfile(f, dest / f.name)
        n += 1
    return n


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
