"""Session store — stroke/event logs are the primary data, images are aids.

    data/sessions/<session_id>/
        metadata.json      identity, task, condition, device, timing, counts, QC
        events.jsonl       append-only operation log
        strokes.jsonl      append-only per-stroke record with sampled points
        feedback.jsonl     append-only record of every feedback shown
        questionnaire.json short 1–5 self-report
        before.png         work submitted before feedback
        after.png          work after the (optional) revision
        final.png          copy of the last submitted work
        snapshots/NNNN_<elapsed_s>s.png     auxiliary key frames

Client records carry a monotonic `seq` per stream; appends drop anything at or
below the stored high-water mark, so an offline client can safely re-send.
"""
import base64
import hashlib
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from . import config          # read through the module: the data dir is env-driven
                             # and tests reload it, so binding the value at import
                             # time would freeze the production path
from .logstore import JsonlLog, read_json, write_json

SCHEMA_VERSION = 2

# Where a session is in its journey from the child's screen to a verified row.
# Separate from `status` (which says where the *child* is): a finished drawing
# whose last batch never uploaded is done for the child and not done for the data.
LIFECYCLE = ("recording", "completed_local", "pending_upload", "uploaded", "server_verified")
_DATAURL_RE = re.compile(r"^data:image/(png|jpeg);base64,(.+)$", re.DOTALL)
_STREAMS = ("events", "strokes", "feedback", "ratings", "annotations")


def now_iso() -> str:
    """UTC, to the millisecond.

    Seconds are not enough: two sessions started in the same second cannot be
    ordered, and the history window (`history.build(before=...)`, which has to
    reproduce exactly what a past decision could see) would silently drop the
    earlier one. Still sorts lexicographically against older second-resolution
    stamps, so existing sessions stay comparable.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def decode_data_url(data_url: str) -> bytes:
    m = _DATAURL_RE.match(data_url.strip())
    if not m:
        raise ValueError("expected a PNG/JPEG data URL")
    return base64.b64decode(m.group(2))


class SessionStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or config.SESSIONS_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths -------------------------------------------------------------
    def dir(self, sid: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", sid):
            raise KeyError(sid)
        return self.root / sid

    def _meta_path(self, sid: str) -> Path:
        d = self.dir(sid)
        legacy = d / "session.json"          # schema 1 sessions stay readable
        return legacy if legacy.exists() and not (d / "metadata.json").exists() else d / "metadata.json"

    def log(self, sid: str, stream: str) -> JsonlLog:
        return JsonlLog(self.dir(sid) / f"{stream}.jsonl")

    # -- lifecycle ---------------------------------------------------------
    def create(self, quest: Dict[str, Any], intent: Dict[str, Any], *,
               participant: Optional[Dict[str, Any]] = None,
               condition: Optional[Dict[str, Any]] = None,
               device: Optional[Dict[str, Any]] = None,
               study: Optional[Dict[str, Any]] = None,
               canvas: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sid = uuid.uuid4().hex[:12]
        d = self.root / sid
        (d / "snapshots").mkdir(parents=True)
        p = dict(participant or {})
        meta = {
            "schema_version": SCHEMA_VERSION,
            "id": sid,
            "session_id": sid,
            "created_at": now_iso(),
            # -- identity: an anonymous device id always, a researcher code when given
            "participant": {
                "anon_id": p.get("anon_id", ""),
                "participant_id": p.get("participant_id", ""),
                "label": p.get("label", ""),
            },
            # -- task: same row the child sees as a level
            "quest_id": quest["id"],
            "task": {
                "task_id": quest["id"],
                # a task is a measurement object: which family, which parallel
                # form, in which prompt style, at which version of the library
                "family": quest.get("family", ""),
                "mission_family": quest.get("family_slug", ""),
                "form_id": quest.get("form_id", ""),
                "prompt_style": quest.get("prompt_style", ""),
                "task_version": quest.get("version", ""),
                "category": quest.get("category"),
                "difficulty": quest.get("difficulty"),
                "time_limit_sec": quest.get("time_limit_sec"),
                "allowed_tools": quest.get("allowed_tools"),
                "stimulus_id": quest.get("stimulus_id", ""),
                "stimulus_kind": (quest.get("stimulus") or {}).get("kind", "none"),
                "stimulus_placeholder": bool(quest.get("stimulus_placeholder")),
                "reference_id": (quest.get("reference") or {}).get("id"),
                "focus_dims": quest.get("focus_dims", []),
                "applicable_dims": quest.get("applicable_dims", []),
                "rubric": quest.get("rubric"),
                "process_targets": quest.get("process_targets", []),
                "order_index": (study or {}).get("order_index"),
                "sequence_id": (study or {}).get("sequence_id", ""),
            },
            # -- condition: frozen at creation, never changed mid-session
            "condition": dict(condition or {}),
            "study": {"active": bool((study or {}).get("active")), "study_id": (study or {}).get("study_id", ""),
                      "group": (study or {}).get("group", "")},
            "app": {"version": __version__, "schema": SCHEMA_VERSION},
            "device": dict(device or {}),
            "canvas": dict(canvas or {}),
            "times": {"created_at": now_iso(), "started_at": None, "ended_at": None, "duration_ms": None},
            "intent": intent,
            "status": "drawing",
            "snapshots": [],
            "before": None,
            "after": None,
            "feedback": None,
            "comparison": None,
            "revised": None,
            "questionnaire": None,
            "lifecycle": "recording",
            "streams": {s: {"last_seq": 0, "count": 0} for s in _STREAMS},
            "counts": {"strokes": 0, "points": 0, "events": 0, "snapshots": 0},
            "qc": None,
        }
        self._write(sid, meta)
        return meta

    # -- lifecycle ---------------------------------------------------------
    def set_lifecycle(self, sid: str, state: str) -> Dict[str, Any]:
        """Advance the upload lifecycle. Never moves backwards.

        A session that reached `uploaded` cannot be demoted by a late duplicate
        batch, and `server_verified` is only ever set by QC.
        """
        meta = self.load(sid)
        cur = meta.get("lifecycle", "recording")
        if state in LIFECYCLE and LIFECYCLE.index(state) > LIFECYCLE.index(cur):
            meta["lifecycle"] = state
            meta.setdefault("lifecycle_at", {})[state] = now_iso()
            self._write(sid, meta)
        return meta

    def log_checksum(self, sid: str) -> Dict[str, Any]:
        """Content hash of the two primary logs.

        Recorded when a session is verified, so later corruption or a partial
        re-upload is detectable rather than silently analysed.
        """
        out: Dict[str, Any] = {}
        for stream in ("events", "strokes"):
            path = self.dir(sid) / f"{stream}.jsonl"
            if path.exists():
                data = path.read_bytes()
                out[stream] = {"sha256": hashlib.sha256(data).hexdigest()[:32], "bytes": len(data)}
        return out

    def load(self, sid: str) -> Dict[str, Any]:
        meta = read_json(self._meta_path(sid))
        if meta is None:
            raise KeyError(sid)
        return meta

    def load_full(self, sid: str) -> Dict[str, Any]:
        """Metadata plus the log streams — what the API hands back."""
        meta = self.load(sid)
        if meta.get("schema_version", 1) >= 2:
            meta["events"] = self.log(sid, "events").read()
            meta["strokes_summary"] = self._strokes_summary(sid)
            meta["feedback_log"] = self.log(sid, "feedback").read()
            meta["ratings"] = self.log(sid, "ratings").read()
            meta["annotations"] = self.log(sid, "annotations").read()
            meta["condition_snapshot"] = self.condition_snapshot(sid)
            meta.setdefault("questionnaire", None)
            meta["questionnaire"] = meta["questionnaire"] or self.self_report(sid)
            meta["personalization"] = self.personalization(sid)
        meta.setdefault("events", [])
        return meta

    # -- personalisation ---------------------------------------------------
    # -- the condition the child actually saw -------------------------------
    def save_condition(self, sid: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Freeze the complete task definition into `condition.json`.

        `tasks.json` gets edited and the library grows; a task_id alone is not
        enough to recover what was on screen. Without this, a later reader
        resolves the id against a definition the child never saw.
        """
        write_json(self.dir(sid) / "condition.json", snapshot)
        return snapshot

    def condition_snapshot(self, sid: str) -> Optional[Dict[str, Any]]:
        return read_json(self.dir(sid) / "condition.json")

    def personalization(self, sid: str) -> Optional[Dict[str, Any]]:
        return read_json(self.dir(sid) / "personalization.json")

    def save_personalization(self, sid: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Freeze what the system knew and decided *before* the child drew.

        Kept in its own file rather than recomputed later on purpose: the
        representation builder will improve, and a decision has to stay
        reproducible against the input it actually had.
        """
        record = dict(record, frozen_at=now_iso())
        write_json(self.dir(sid) / "personalization.json", record)
        meta = self.load(sid)
        meta["history_mode"] = record.get("requested_mode", "none")
        meta["personalization_backend"] = record.get("backend")
        self._write(sid, meta)
        return record

    def record_prediction_outcome(self, sid: str, answers: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Score the prediction written down at task start against the self-report.

        This is what turns three conditions into an evaluation: every arm wrote
        a number before the child drew, and here is the answer.
        """
        rec = self.personalization(sid)
        if not rec:
            return None
        pred = rec.get("prediction") or {}
        outcome, error = {}, {}
        for key in ("difficulty", "confidence"):
            actual, guess = answers.get(key), pred.get(key)
            if isinstance(actual, (int, float)) and isinstance(guess, (int, float)):
                outcome[key] = actual
                error[key] = round(guess - actual, 3)
        rec["outcome"] = outcome
        rec["error"] = error
        rec["scored_at"] = now_iso()
        write_json(self.dir(sid) / "personalization.json", rec)
        return rec

    def _write(self, sid: str, meta: Dict[str, Any]) -> None:
        write_json(self.dir(sid) / "metadata.json", meta)

    def list(self) -> List[Dict[str, Any]]:
        keys = ("id", "created_at", "quest_id", "status", "revised")
        out = []
        for d in self.root.iterdir():
            if not d.is_dir():
                continue
            m = read_json(d / "metadata.json") or read_json(d / "session.json")
            if not m:
                continue
            row = {k: m.get(k) for k in keys}
            p = m.get("participant")
            row["participant"] = p if isinstance(p, str) else (p or {}).get("participant_id") or (p or {}).get("anon_id", "")
            row["task_id"] = m.get("quest_id")
            row["qc_ok"] = (m.get("qc") or {}).get("ok")
            out.append(row)
        return sorted(out, key=lambda r: r.get("created_at") or "", reverse=True)

    # -- log streams -------------------------------------------------------
    def append_client(self, sid: str, stream: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Idempotent ingest of a client batch. Returns the new stream state."""
        if stream not in _STREAMS:
            raise ValueError(f"unknown stream: {stream}")
        meta = self.load(sid)
        state = meta.setdefault("streams", {}).setdefault(stream, {"last_seq": 0, "count": 0})
        prev = int(state.get("last_seq", 0))
        stamped = [dict(r, src=r.get("src", "client"), ts=r.get("ts") or now_iso()) for r in records]
        fresh = [r for r in stamped if int(r.get("seq") or 0) > prev]
        written, skipped, last = self.log(sid, stream).append_after(stamped, prev)
        state["last_seq"], state["count"] = last, int(state.get("count", 0)) + written
        counts = meta.setdefault("counts", {})
        if stream == "strokes":
            counts["strokes"] = state["count"]
            counts["points"] = int(counts.get("points", 0)) + sum(len(r.get("points") or []) for r in fresh)
        elif stream == "events":
            counts["events"] = state["count"]
        self._write(sid, meta)
        return {"stream": stream, "written": written, "skipped": skipped, "last_seq": last, "count": state["count"]}

    def add_server_event(self, sid: str, type_: str, t_ms: int = 0, payload: Optional[Dict[str, Any]] = None) -> None:
        """Log something the server did (feedback shown, revision skipped, …)."""
        self.log(sid, "events").append([
            {"seq": None, "src": "server", "ts": now_iso(), "t_ms": t_ms, "type": type_, "payload": payload}])
        meta = self.load(sid)
        meta.setdefault("counts", {})["events"] = self.log(sid, "events").count()
        self._write(sid, meta)

    def add_feedback(self, sid: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Append a structured feedback record (source / type / text / region)."""
        meta = self.load(sid)
        state = meta.setdefault("streams", {}).setdefault("feedback", {"last_seq": 0, "count": 0})
        rec = {
            "feedback_id": f"fb_{uuid.uuid4().hex[:8]}",
            "seq": None,
            "src": "server",
            "ts": now_iso(),
            "session_id": sid,
            "t_ms": record.get("t_ms", 0),
            "phase": record.get("phase", "before"),
            "source": record.get("source", "ai"),      # ai | teacher | self
            "feedback_type": record.get("feedback_type", "text"),
            "backend": record.get("backend", ""),
            "text": record.get("text", ""),
            "target_region": record.get("target_region"),
            "shown_at": record.get("shown_at") or now_iso(),
        }
        self.log(sid, "feedback").append([rec])
        state["count"] = int(state.get("count", 0)) + 1
        self._write(sid, meta)
        return rec

    def add_rating(self, sid: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Append a human rating. Append-only and rater-tagged on purpose:
        two teachers rating the same artwork is the normal case, and
        inter-rater agreement is something a dataset has to be able to report.
        """
        meta = self.load(sid)
        state = meta.setdefault("streams", {}).setdefault("ratings", {"last_seq": 0, "count": 0})
        rec = dict(record)
        rec.update({"rating_id": f"rt_{uuid.uuid4().hex[:8]}", "seq": None, "src": "server",
                    "ts": now_iso(), "session_id": sid})
        self.log(sid, "ratings").append([rec])
        state["count"] = int(state.get("count", 0)) + 1
        meta.setdefault("counts", {})["ratings"] = state["count"]
        self._write(sid, meta)
        return rec

    def add_annotation(self, sid: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Append one expert span. Append-only and rater-tagged, like ratings."""
        meta = self.load(sid)
        state = meta.setdefault("streams", {}).setdefault("annotations", {"last_seq": 0, "count": 0})
        rec = dict(record)
        rec.update({"annotation_id": f"an_{uuid.uuid4().hex[:8]}", "seq": None,
                    "src": "server", "ts": now_iso(), "session_id": sid})
        self.log(sid, "annotations").append([rec])
        state["count"] = int(state.get("count", 0)) + 1
        meta.setdefault("counts", {})["annotations"] = state["count"]
        self._write(sid, meta)
        return rec

    def _strokes_summary(self, sid: str) -> Dict[str, Any]:
        log = self.log(sid, "strokes")
        rows = log.read()
        return {
            "count": len(rows),
            "points": sum(len(r.get("points") or []) for r in rows),
            "tools": sorted({r.get("tool") for r in rows if r.get("tool")}),
            "colors": sorted({r.get("color") for r in rows if r.get("color")}),
            "last_t_ms": max((r.get("t_end_ms") or 0) for r in rows) if rows else 0,
        }

    # -- images ------------------------------------------------------------
    def add_snapshot(self, sid: str, png: bytes, elapsed_ms: int) -> str:
        meta = self.load(sid)
        idx = len(meta.get("snapshots", [])) + 1
        name = f"{idx:04d}_{elapsed_ms // 1000}s.png"
        (self.dir(sid) / "snapshots" / name).write_bytes(png)
        meta.setdefault("snapshots", []).append({"file": f"snapshots/{name}", "elapsed_ms": elapsed_ms, "at": now_iso()})
        meta.setdefault("counts", {})["snapshots"] = len(meta["snapshots"])
        self._write(sid, meta)
        return name

    def save_phase_image(self, sid: str, phase: str, png: bytes) -> Path:
        p = self.dir(sid) / f"{phase}.png"
        p.write_bytes(png)
        if phase in ("before", "after"):
            (self.dir(sid) / "final.png").write_bytes(png)  # last submitted work
        return p

    def read_image(self, sid: str, phase: str) -> Optional[bytes]:
        p = self.dir(sid) / f"{phase}.png"
        return p.read_bytes() if p.exists() else None

    # -- mutations ---------------------------------------------------------
    def update(self, sid: str, **fields: Any) -> Dict[str, Any]:
        meta = self.load(sid)
        meta.update(fields)
        self._write(sid, meta)
        return meta

    def mark_started(self, sid: str, at_iso: str = "") -> None:
        meta = self.load(sid)
        times = meta.setdefault("times", {})
        if not times.get("started_at"):
            times["started_at"] = at_iso or now_iso()
            self._write(sid, meta)

    def mark_ended(self, sid: str, duration_ms: Optional[int] = None) -> Dict[str, Any]:
        meta = self.load(sid)
        times = meta.setdefault("times", {})
        times["ended_at"] = now_iso()
        if duration_ms is not None:
            times["duration_ms"] = duration_ms
        self._write(sid, meta)
        return meta

    def self_report(self, sid: str) -> Optional[Dict[str, Any]]:
        """The child's own answers — `self_report.json`, or the older name."""
        d = self.dir(sid)
        return read_json(d / "self_report.json") or read_json(d / "questionnaire.json")

    def save_quality(self, sid: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """`quality.json` beside the data it judges, not only inside metadata."""
        write_json(self.dir(sid) / "quality.json", result)
        return result

    def copy_reference(self, sid: str, quest: Dict[str, Any]) -> Optional[str]:
        """Keep the stimulus the child saw inside the session directory.

        The file in `static/refs/` will be replaced when a real stimulus lands;
        a session that points at a path is not self-contained, and the artwork
        would end up next to an image nobody showed this child.
        """
        ref = quest.get("reference") or {}
        url = (ref.get("file") or "").lstrip("/")
        if not url:
            return None
        src = config.BASE_DIR / url
        if not src.exists():
            return None
        dest_dir = self.dir(sid) / "reference"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copyfile(src, dest)
        return f"reference/{src.name}"

    def save_questionnaire(self, sid: str, answers: Dict[str, Any]) -> Dict[str, Any]:
        rec = dict(answers, session_id=sid, at=now_iso())
        write_json(self.dir(sid) / "self_report.json", rec)
        self.update(sid, questionnaire=rec)
        return rec
