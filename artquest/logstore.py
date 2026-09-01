"""Append-only process logs — the primary research data.

The stroke/event logs are the source of truth; canvas screenshots are only an
aid. Everything a session produces lives in one directory:

    data/sessions/<session_id>/
        metadata.json      identity, task, condition, device, timing, QC
        events.jsonl       one JSON object per line, append-only
        strokes.jsonl      one JSON object per line, append-only
        feedback.jsonl     every feedback shown, append-only
        questionnaire.json short self-report
        before.png / after.png / final.png
        snapshots/         auxiliary key frames

Every record carries a client-assigned ``seq`` that is monotonic within its
stream. Appends drop records whose seq was already stored, so a client that
buffered locally and lost its connection can safely re-send a batch.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# How much of the file's tail we read to recover the last stored seq.
_TAIL_BYTES = 65536


class JsonlLog:
    """An append-only JSON Lines stream with idempotent, seq-ordered appends."""

    def __init__(self, path: Path):
        self.path = Path(path)

    # -- reading -----------------------------------------------------------
    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:  # tolerate a torn final line
                    continue
        return out

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("rb") as fh:
            return sum(1 for line in fh if line.strip())

    def last_seq(self) -> int:
        """Highest seq already stored, read from the file's tail (0 if empty)."""
        if not self.path.exists():
            return 0
        size = self.path.stat().st_size
        if size == 0:
            return 0
        with self.path.open("rb") as fh:
            fh.seek(max(0, size - _TAIL_BYTES))
            chunk = fh.read()
        for line in reversed(chunk.decode("utf-8", "ignore").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                seq = json.loads(line).get("seq")
            except json.JSONDecodeError:
                continue
            if seq is not None:  # server-side records carry no seq
                return int(seq)
        return 0

    # -- writing -----------------------------------------------------------
    def _write(self, records: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def append(self, records: Iterable[Dict[str, Any]]) -> int:
        """Append records as-is (used for server-side records without a seq)."""
        records = [r for r in records if isinstance(r, dict)]
        if records:
            self._write(records)
        return len(records)

    def append_after(self, records: Iterable[Dict[str, Any]], last_seq: int) -> Tuple[int, int, int]:
        """Append client records in seq order, dropping ones at or below `last_seq`.

        Returns ``(written, skipped, new_last_seq)``. A client that buffered
        locally and lost its connection can re-send a batch without duplicating
        rows. Records are fsync'd, so an acknowledged batch survives a crash.
        """
        records = [r for r in records if isinstance(r, dict)]
        if not records:
            return 0, 0, last_seq
        records.sort(key=lambda r: int(r.get("seq") or 0))
        fresh = [r for r in records if int(r.get("seq") or 0) > last_seq]
        skipped = len(records) - len(fresh)
        if not fresh:
            return 0, skipped, last_seq
        self._write(fresh)
        return len(fresh), skipped, int(fresh[-1].get("seq") or last_seq)


def write_json(path: Path, data: Any) -> None:
    """Atomic small-file write (metadata, questionnaire)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> Optional[Any]:
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
