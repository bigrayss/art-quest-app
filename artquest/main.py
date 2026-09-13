"""FastAPI application: serves the drawing UI and the session / research API."""
import logging
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import history as history_mod
from . import study as study_mod
from .config import SESSIONS_DIR, SNAPSHOT_INTERVAL_SEC, STATIC_DIR, claude_available
from .feedback import get_feedback_engine
from .personalize import MODES as HISTORY_MODES, get_personalizer
from .qc import check as qc_check
from .quests import EMOTIONS, QUESTS, QUESTS_BY_ID
from .reconstruct import check_final
from .revision import attribute as attribute_revision
from .schemas import (CreateSession, DrawEvent, FeedbackIn, Finalize, LogBatch,
                      Questionnaire, Rating, Snapshot, StudyAssign, Stroke, Submit)
from .scoring import DIMENSIONS, SCALE_MAX, get_scorer
from .storage import SCHEMA_VERSION, SessionStore, decode_data_url, now_iso

log = logging.getLogger("artquest")

app = FastAPI(title="ArtQuest", version=__version__)
store = SessionStore()
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/files", StaticFiles(directory=SESSIONS_DIR), name="files")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _session_or_404(sid: str) -> Dict[str, Any]:
    try:
        return store.load(sid)
    except KeyError:
        raise HTTPException(404, "session not found")


def _ingest(sid: str, events: List[DrawEvent], strokes: List[Stroke]) -> Dict[str, Any]:
    """Append a client batch to the append-only logs (idempotent by seq)."""
    out = {}
    if events:
        out["events"] = store.append_client(sid, "events", [e.record() for e in events])
    if strokes:
        out["strokes"] = store.append_client(sid, "strokes", [s.model_dump() for s in strokes])
    return out


def _run_qc(sid: str, pending: int = 0) -> Dict[str, Any]:
    meta = store.load(sid)
    try:
        # rebuild the artwork from the logs and hold it against what was saved
        replay = check_final(store.dir(sid))
    except Exception:
        log.exception("reconstruction failed for %s", sid)
        replay = None
    result = qc_check(
        meta,
        strokes=store._strokes_summary(sid),
        events=store.log(sid, "events").count(),
        known_task=meta.get("quest_id") in QUESTS_BY_ID,
        has_final_image=(store.dir(sid) / "final.png").exists(),
        pending_uploads=pending,
        replay=replay,
    )
    result["at"] = now_iso()
    store.update(sid, qc=result)
    if not result["ok"]:
        log.warning("session %s failed QC: %s", sid, result["failed"])
    return result


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def config():
    scorer, fb = get_scorer(), get_feedback_engine()
    st = study_mod.load_study()
    return {
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "snapshot_interval_sec": SNAPSHOT_INTERVAL_SEC,
        "scorer": scorer.name,
        "feedback": fb.name,
        "claude_available": claude_available(),
        "dimensions": DIMENSIONS,
        "scale_max": SCALE_MAX,
        "emotions": EMOTIONS,
        "default_condition": study_mod.DEFAULT_CONDITION,
        "history_modes": list(HISTORY_MODES),
        "study": {"active": st["active"], "study_id": st["study_id"], "order": st["order"]},
    }


@app.get("/api/quests")
def quests():
    return QUESTS


# -- study mode ------------------------------------------------------------
@app.get("/api/study")
def study_config():
    return study_mod.load_study()


@app.post("/api/study/assign")
def study_assign(body: StudyAssign):
    """Register a participant code and hand back their counterbalanced order."""
    return study_mod.assign(body.participant_id, body.anon_id, body.group)


# -- sessions --------------------------------------------------------------
@app.get("/api/sessions")
def list_sessions():
    return store.list()


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    try:
        return store.load_full(sid)
    except KeyError:
        raise HTTPException(404, "session not found")


@app.get("/api/sessions/{sid}/strokes")
def get_strokes(sid: str):
    """Raw stroke log — enough on its own to replay the whole drawing."""
    _session_or_404(sid)
    return store.log(sid, "strokes").read()


def _personalize(sid: str, quest: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    """Build this child's representation and let the arm decide, before they draw.

    The representation is rebuilt from the logs every time (so it always
    reflects the current builder) but the copy used here is frozen into the
    session — `history.build(before=...)` with this session's timestamp
    reproduces the same input later.
    """
    cond = meta.get("condition") or {}
    mode = cond.get("history_mode", "none")
    who = meta.get("participant") or {}
    rep = None
    if mode != "none":
        try:
            rep = history_mod.build(who.get("participant_id", ""), who.get("anon_id", ""),
                                    before=meta.get("created_at") or "")
        except Exception:
            log.exception("representation build failed for %s", sid)
    try:
        decision = get_personalizer(mode).prepare(quest, rep)
    except Exception as e:                      # an arm must never lose the session
        log.exception("personalizer failed")
        decision = {"requested_mode": mode, "backend": "error", "available": False,
                    "note": str(e), "history_used": {}, "shown": [], "prediction": {}}
    # the whole representation goes in: a decision is only reproducible next to
    # the state it was made from
    decision["representation"] = rep
    return store.save_personalization(sid, decision)


@app.post("/api/sessions", status_code=201)
def create_session(body: CreateSession):
    quest = QUESTS_BY_ID.get(body.task())
    if quest is None:
        raise HTTPException(400, "unknown quest")
    st = body.study.model_dump()
    condition = study_mod.resolve_condition(body.condition, st.get("group", ""))
    if quest.get("time_limit_sec") and not condition.get("time_limit_sec"):
        condition["time_limit_sec"] = quest["time_limit_sec"]
    meta = store.create(
        quest, body.intent.model_dump(),
        participant=body.participant_dict(), condition=condition,
        device=body.device.model_dump(), study=st, canvas=body.canvas.model_dump(),
    )
    store.mark_started(meta["id"])
    store.add_server_event(meta["id"], "SESSION_START", 0, {
        "task_id": quest["id"], "condition": condition, "study_id": st.get("study_id", "")})
    personalization = _personalize(meta["id"], quest, meta)
    if personalization.get("shown"):
        store.add_server_event(meta["id"], "HISTORY_SHOWN", 0, {
            "backend": personalization.get("backend"),
            "requested_mode": personalization.get("requested_mode"),
            "n_lines": len(personalization["shown"]),
            "n_prior_tasks": (personalization.get("history_used") or {}).get("n_tasks", 0)})
    return {"session_id": meta["id"], "session": store.load(meta["id"]),
            # the client only needs what to show; the representation stays server-side
            "personalization": {k: personalization.get(k) for k in
                                ("requested_mode", "backend", "available", "shown", "history_used")}}


@app.post("/api/sessions/{sid}/log")
def ingest_log(sid: str, body: LogBatch):
    """Batched, idempotent ingest of buffered strokes and events.

    The client writes to local storage first and flushes here; re-sending a
    batch after a dropped connection cannot duplicate rows.
    """
    _session_or_404(sid)
    return {"ok": True, "streams": _ingest(sid, body.events, body.strokes)}


@app.post("/api/sessions/{sid}/snapshot")
def snapshot(sid: str, body: Snapshot):
    _session_or_404(sid)
    try:
        png = decode_data_url(body.image)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _ingest(sid, body.events, [])
    name = store.add_snapshot(sid, png, body.elapsed_ms)
    return {"ok": True, "file": name}


def _score_and_save(sid: str, phase: str, png: bytes, elapsed_ms: int) -> Dict[str, Any]:
    meta = store.load(sid)
    quest, intent = QUESTS_BY_ID[meta["quest_id"]], meta["intent"]
    store.save_phase_image(sid, phase, png)
    try:
        scores = get_scorer().score(png, quest, intent)
    except Exception as e:  # scoring must never lose the artwork
        log.exception("scoring failed")
        scores = {"backend": "error", "scale": [1, SCALE_MAX], "dims": {}, "summary": f"评分失败：{e}"}
    return {"file": f"{phase}.png", "elapsed_ms": elapsed_ms, "at": now_iso(), "scores": scores}


@app.post("/api/sessions/{sid}/submit")
def submit(sid: str, body: Submit):
    meta = _session_or_404(sid)
    try:
        png = decode_data_url(body.image)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _ingest(sid, body.events, body.strokes)
    quest, intent = QUESTS_BY_ID[meta["quest_id"]], meta["intent"]
    engine = get_feedback_engine()

    if body.phase == "before":
        if meta.get("before"):
            raise HTTPException(409, "before already submitted")
        record = _score_and_save(sid, "before", png, body.elapsed_ms)
        try:
            fb = engine.feedback(png, quest, intent, record["scores"])
        except Exception as e:
            log.exception("feedback failed")
            fb = {"backend": "error", "text": f"反馈生成失败：{e}"}
        fb["at"] = now_iso()
        # structured record + the anchor that splits "before feedback" from "after"
        entry = store.add_feedback(sid, {"t_ms": body.elapsed_ms, "phase": "before", "source": "ai",
                                         "feedback_type": "formative", "backend": fb["backend"], "text": fb["text"]})
        fb["feedback_id"] = entry["feedback_id"]
        fb["t_ms"] = body.elapsed_ms
        store.add_server_event(sid, "FEEDBACK_SHOWN", body.elapsed_ms,
                               {"feedback_id": entry["feedback_id"], "backend": fb["backend"], "phase": "before"})
        meta = store.update(sid, before=record, feedback=fb, status="feedback")
        return {"phase": "before", "scores": record["scores"], "feedback": fb, "session": meta}

    # phase == "after"
    if not meta.get("before"):
        raise HTTPException(409, "submit before first")
    if meta.get("after"):
        raise HTTPException(409, "after already submitted")
    record = _score_and_save(sid, "after", png, body.elapsed_ms)
    before_png = store.read_image(sid, "before")
    try:
        cmp = engine.compare(before_png, png, meta["before"]["scores"], record["scores"], quest, intent)
    except Exception as e:
        log.exception("compare failed")
        cmp = {"backend": "error", "text": f"对比生成失败：{e}"}
    store.add_feedback(sid, {"t_ms": body.elapsed_ms, "phase": "after", "source": "ai",
                             "feedback_type": "comparison", "backend": cmp["backend"], "text": cmp["text"]})
    store.add_server_event(sid, "SESSION_END", body.elapsed_ms, {"revised": True})
    store.update(sid, after=record, comparison=cmp, revised=True, status="done")
    store.mark_ended(sid, body.elapsed_ms)
    qc = _run_qc(sid, body.pending)
    return {"phase": "after", "scores": record["scores"], "comparison": cmp, "session": store.load_full(sid), "qc": qc}


@app.post("/api/sessions/{sid}/finalize")
def finalize(sid: str, body: Finalize):
    """Finish without revising: `after` is a copy of `before`."""
    meta = _session_or_404(sid)
    if not meta.get("before"):
        raise HTTPException(409, "submit before first")
    if meta.get("after"):
        return {"session": meta}
    _ingest(sid, body.events, body.strokes)
    # declining to revise is an outcome of *that* feedback, not an absence of data
    last_fb = meta.get("feedback") or {}
    store.add_server_event(sid, "REVISION_SKIPPED", body.elapsed_ms, {
        "feedback_id": last_fb.get("feedback_id"),
        "latency_ms": body.elapsed_ms - (last_fb.get("t_ms") or 0) if last_fb.get("feedback_id") else None})
    png = store.read_image(sid, "before")
    store.save_phase_image(sid, "after", png)
    record = dict(meta["before"], file="after.png", elapsed_ms=body.elapsed_ms, at=now_iso())
    store.add_server_event(sid, "SESSION_END", body.elapsed_ms, {"revised": False})
    store.update(sid, after=record, revised=False, status="done")
    store.mark_ended(sid, body.elapsed_ms)
    qc = _run_qc(sid, body.pending)
    return {"session": store.load_full(sid), "qc": qc}


@app.post("/api/sessions/{sid}/questionnaire")
def questionnaire(sid: str, body: Questionnaire):
    _session_or_404(sid)
    answers = body.model_dump()
    rec = store.save_questionnaire(sid, {k: v for k, v in answers.items() if k != "t_ms"})
    store.add_server_event(sid, "QUESTIONNAIRE_SUBMITTED", body.t_ms,
                           {k: v for k, v in rec.items() if isinstance(v, int)})
    # the self-report is the label the pre-task prediction was written against
    scored = store.record_prediction_outcome(sid, rec)
    return {"ok": True, "questionnaire": rec,
            "prediction_error": (scored or {}).get("error")}


@app.post("/api/sessions/{sid}/feedback")
def add_feedback(sid: str, body: FeedbackIn):
    """Record a teacher's or the child's own feedback next to the AI's.

    `target_region` is in canvas pixel space, the same coordinates strokes use,
    so `/revision` can answer whether the child then worked where it pointed.
    """
    _session_or_404(sid)
    rec = store.add_feedback(sid, body.model_dump())
    store.add_server_event(sid, "FEEDBACK_SHOWN", body.t_ms,
                           {"feedback_id": rec["feedback_id"], "source": body.source, "phase": body.phase,
                            "has_region": bool(body.target_region)})
    return {"ok": True, "feedback": rec}


@app.post("/api/sessions/{sid}/rating")
def add_rating(sid: str, body: Rating):
    """A teacher's / expert's rating of the artwork — a second rater, not the child."""
    _session_or_404(sid)
    rec = store.add_rating(sid, body.model_dump())
    store.add_server_event(sid, "RATING_ADDED", body.t_ms,
                           {"rating_id": rec["rating_id"], "source": body.source,
                            "rater_id": body.rater_id, "overall": body.overall,
                            "n_dims": len(body.dims)})
    return {"ok": True, "rating": rec}


@app.get("/api/sessions/{sid}/revision")
def get_revision(sid: str):
    """Feedback → what the child did next, in time and (when targeted) in space.

    Derived from the logs on request, never stored: the relation improves when
    the analysis does.
    """
    _session_or_404(sid)
    return attribute_revision(store.dir(sid))


@app.get("/api/sessions/{sid}/personalization")
def get_personalization(sid: str):
    """Exactly what the system knew and decided before this child drew."""
    _session_or_404(sid)
    rec = store.personalization(sid)
    if rec is None:
        raise HTTPException(404, "no personalization recorded for this session")
    return rec


# -- participants: behavioural history → user representation ------------------
@app.get("/api/participants/{pid}/history")
def participant_history(pid: str, anon_id: str = "", before: str = ""):
    """A participant's finished tasks, compacted — the input to a representation."""
    metas = history_mod.sessions_for(pid, anon_id, before=before)
    return {"participant_id": pid, "anon_id": anon_id, "n_tasks": len(metas),
            "tasks": [history_mod.task_record(m) for m in metas]}


@app.get("/api/participants/{pid}/representation")
def participant_representation(pid: str, anon_id: str = "", before: str = ""):
    """Rebuilt from the logs on every call — never a stored summary.

    `before` (ISO timestamp) reproduces the input a past decision had.
    """
    return history_mod.build(pid, anon_id, before=before)


@app.post("/api/sessions/{sid}/qc")
def rerun_qc(sid: str):
    _session_or_404(sid)
    return _run_qc(sid)
