"""Append-only process logs — the primary research data.

The stroke/event logs are the source of truth; canvas screenshots are only an
aid. The session directory is laid out in `storage.py`; this module is only the
append-only JSON Lines mechanism underneath it.

Every record carries a client-assigned ``seq`` that is monotonic within its
stream. Appends drop records whose seq was already stored, so a client that
buffered locally and lost its connection can safely re-send a batch.

A finished stream is gzipped in place (`strokes.jsonl` -> `strokes.jsonl.gz`).
Reads are transparent; a late append thaws the file first, so compression is
never a decision a caller has to think about.
"""
import gzip
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# How much of the file's tail we read to recover the last stored seq.
_TAIL_BYTES = 65536


class JsonlLog:
    """An append-only JSON Lines stream with idempotent, seq-ordered appends."""

    def __init__(self, path: Path):
        self.path = Path(path)                       # the plain .jsonl path
        self.gz_path = Path(str(path) + ".gz")

    # -- reading -----------------------------------------------------------
    def exists(self) -> bool:
        return self.path.exists() or self.gz_path.exists()

    def _open_text(self):
        """Whichever of the two forms is on disk, as a text stream."""
        if self.path.exists():
            return self.path.open("r", encoding="utf-8")
        return gzip.open(self.gz_path, "rt", encoding="utf-8")

    def read(self) -> List[Dict[str, Any]]:
        if not self.exists():
            return []
        out = []
        with self._open_text() as fh:
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
        if not self.exists():
            return 0
        with self._open_text() as fh:
            return sum(1 for line in fh if line.strip())

    # -- compression -------------------------------------------------------
    def compress(self) -> bool:
        """Gzip a finished stream in place. Idempotent; returns True if it ran."""
        if not self.path.exists():
            return False
        data = self.path.read_bytes()
        tmp = Path(str(self.gz_path) + ".tmp")
        with gzip.open(tmp, "wb", compresslevel=6) as fh:
            fh.write(data)
        tmp.replace(self.gz_path)
        self.path.unlink()
        return True

    def thaw(self) -> bool:
        """Undo `compress` so the stream can be appended to again."""
        if self.path.exists() or not self.gz_path.exists():
            return False
        with gzip.open(self.gz_path, "rb") as fh:
            data = fh.read()
        tmp = Path(str(self.path) + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(self.path)
        self.gz_path.unlink()
        return True

    def last_seq(self) -> int:
        """Highest seq already stored, read from the file's tail (0 if empty)."""
        if not self.path.exists():
            # compressed: no cheap tail seek, and a finished stream is small
            return max([int(r["seq"]) for r in self.read() if r.get("seq") is not None] or [0])
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
        self.thaw()                                  # a late batch reopens a finished stream
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


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """One JSON object per line, from either `<path>` or `<path>.gz`."""
    return JsonlLog(path).read()


def read_json(path: Path) -> Optional[Any]:
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
