"""File-based session store.

data/sessions/<session_id>/
    session.json        metadata, intent, timeline, scores, feedback
    snapshots/NNNN_<elapsed_s>s.png
    before.png          submitted work before AI feedback
    after.png           work after the (optional) revision
"""
import base64
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import SESSIONS_DIR

_DATAURL_RE = re.compile(r"^data:image/(png|jpeg);base64,(.+)$", re.DOTALL)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decode_data_url(data_url: str) -> bytes:
    m = _DATAURL_RE.match(data_url.strip())
    if not m:
        raise ValueError("expected a PNG/JPEG data URL")
    return base64.b64decode(m.group(2))


class SessionStore:
    def __init__(self, root: Path = SESSIONS_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths -------------------------------------------------------------
    def dir(self, sid: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", sid):
            raise KeyError(sid)
        return self.root / sid

    def _meta_path(self, sid: str) -> Path:
        return self.dir(sid) / "session.json"

    # -- lifecycle ---------------------------------------------------------
    def create(self, quest_id: str, intent: Dict[str, Any], participant: str = "") -> Dict[str, Any]:
        sid = uuid.uuid4().hex[:12]
        d = self.root / sid
        (d / "snapshots").mkdir(parents=True)
        meta = {
            "id": sid,
            "created_at": now_iso(),
            "quest_id": quest_id,
            "participant": participant,
            "intent": intent,
            "status": "drawing",
            "snapshots": [],
            "events": [],
            "before": None,
            "after": None,
            "feedback": None,
            "comparison": None,
            "revised": None,
        }
        self._write(sid, meta)
        return meta

    def load(self, sid: str) -> Dict[str, Any]:
        p = self._meta_path(sid)
        if not p.exists():
            raise KeyError(sid)
        return json.loads(p.read_text(encoding="utf-8"))

    def _write(self, sid: str, meta: Dict[str, Any]) -> None:
        self._meta_path(sid).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for p in sorted(self.root.glob("*/session.json"), reverse=True):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            out.append({k: m.get(k) for k in ("id", "created_at", "quest_id", "participant", "status", "revised")})
        return out

    # -- mutations ---------------------------------------------------------
    def add_events(self, sid: str, events: List[Dict[str, Any]]) -> None:
        if not events:
            return
        meta = self.load(sid)
        meta["events"].extend(events)
        self._write(sid, meta)

    def add_snapshot(self, sid: str, png: bytes, elapsed_ms: int) -> str:
        meta = self.load(sid)
        idx = len(meta["snapshots"]) + 1
        name = f"{idx:04d}_{elapsed_ms // 1000}s.png"
        (self.dir(sid) / "snapshots" / name).write_bytes(png)
        meta["snapshots"].append({"file": f"snapshots/{name}", "elapsed_ms": elapsed_ms, "at": now_iso()})
        self._write(sid, meta)
        return name

    def save_phase_image(self, sid: str, phase: str, png: bytes) -> Path:
        p = self.dir(sid) / f"{phase}.png"
        p.write_bytes(png)
        return p

    def update(self, sid: str, **fields: Any) -> Dict[str, Any]:
        meta = self.load(sid)
        meta.update(fields)
        self._write(sid, meta)
        return meta

    def read_image(self, sid: str, phase: str) -> Optional[bytes]:
        p = self.dir(sid) / f"{phase}.png"
        return p.read_bytes() if p.exists() else None
