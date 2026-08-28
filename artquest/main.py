"""FastAPI application: serves the drawing UI and the Stage 1 session API."""
import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import SESSIONS_DIR, SNAPSHOT_INTERVAL_SEC, STATIC_DIR, claude_available
from .feedback import get_feedback_engine
from .quests import EMOTIONS, QUESTS, QUESTS_BY_ID
from .schemas import CreateSession, Finalize, Snapshot, Submit
from .scoring import DIMENSIONS, SCALE_MAX, get_scorer
from .storage import SessionStore, decode_data_url, now_iso

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


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def config():
    scorer, fb = get_scorer(), get_feedback_engine()
    return {
        "version": __version__,
        "snapshot_interval_sec": SNAPSHOT_INTERVAL_SEC,
        "scorer": scorer.name,
        "feedback": fb.name,
        "claude_available": claude_available(),
        "dimensions": DIMENSIONS,
        "scale_max": SCALE_MAX,
        "emotions": EMOTIONS,
    }


@app.get("/api/quests")
def quests():
    return QUESTS


@app.get("/api/sessions")
def list_sessions():
    return store.list()


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    return _session_or_404(sid)


@app.post("/api/sessions", status_code=201)
def create_session(body: CreateSession):
    if body.quest_id not in QUESTS_BY_ID:
        raise HTTPException(400, "unknown quest")
    meta = store.create(body.quest_id, body.intent.model_dump(), body.participant)
    return {"session_id": meta["id"], "session": meta}


@app.post("/api/sessions/{sid}/snapshot")
def snapshot(sid: str, body: Snapshot):
    _session_or_404(sid)
    try:
        png = decode_data_url(body.image)
    except ValueError as e:
        raise HTTPException(400, str(e))
    store.add_events(sid, [e.model_dump() for e in body.events])
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
    store.add_events(sid, [e.model_dump() for e in body.events])
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
        store.add_events(sid, [{"t_ms": body.elapsed_ms, "type": "feedback_shown", "detail": {"backend": fb["backend"]}}])
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
    meta = store.update(sid, after=record, comparison=cmp, revised=True, status="done")
    return {"phase": "after", "scores": record["scores"], "comparison": cmp, "session": meta}


@app.post("/api/sessions/{sid}/finalize")
def finalize(sid: str, body: Finalize):
    """Finish without revising: `after` is a copy of `before`."""
    meta = _session_or_404(sid)
    if not meta.get("before"):
        raise HTTPException(409, "submit before first")
    if meta.get("after"):
        return {"session": meta}
    store.add_events(sid, [e.model_dump() for e in body.events] + [{"t_ms": body.elapsed_ms, "type": "revision_skipped", "detail": None}])
    png = store.read_image(sid, "before")
    store.save_phase_image(sid, "after", png)
    record = dict(meta["before"], file="after.png", elapsed_ms=body.elapsed_ms, at=now_iso())
    meta = store.update(sid, after=record, revised=False, status="done")
    return {"session": meta}
