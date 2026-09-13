"""Replay a session from its logs — proof that the log is the primary data.

Reconstruction walks the **event timeline**, not the raw stroke list: strokes
the child undid or cleared are in `strokes.jsonl` for ever (nothing is rewritten
there) but must not appear on the rebuilt artwork. See `artquest/reconstruct.py`.

If a drawing can be rebuilt from the logs alone, the log is complete; key frames
(10/25/50/75/100 %) never have to be stored, they are regenerated on demand.

    python3 tools/replay.py <session_id> [--out DIR] [--keyframes]
    python3 tools/replay.py --all --check     # verify every session replays
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artquest import config  # noqa: E402
from artquest.qc import MAX_REPLAY_REL_DIFF  # noqa: E402
from artquest.reconstruct import check_final, rebuild, render  # noqa: E402

KEYFRAME_PCTS = (10, 25, 50, 75, 100)


def replay_session(sid: str, out_dir: Path = None, keyframes: bool = False) -> Dict[str, Any]:
    d = config.SESSIONS_DIR / sid
    if not (d / "metadata.json").exists():
        raise FileNotFoundError(2, "no such file", str(d / "metadata.json"))
    built = rebuild(d)
    out = out_dir or (d / "replay")
    out.mkdir(parents=True, exist_ok=True)
    built["image"].save(out / "replay.png")

    strokes, frames = built["strokes"], []
    if keyframes and strokes:
        for pct in KEYFRAME_PCTS:
            n = max(1, round(len(strokes) * pct / 100))
            render(strokes, built["size"], n, stimulus=built.get("stimulus")).save(
                out / f"keyframe_{pct:03d}.png")
            frames.append(pct)

    report = {"session_id": sid, "canvas": list(built["size"]),
              "points": built["points"], "keyframes": frames}
    report.update(check_final(d, built))
    rel, streams = report.get("rel"), report.get("streams") or {}
    report["replayable"] = (bool(strokes)
                            and streams.get("status") != "mismatch"
                            and (rel is None or rel <= MAX_REPLAY_REL_DIFF))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session_id", nargs="?")
    ap.add_argument("--all", action="store_true", help="every session in the data dir")
    ap.add_argument("--keyframes", action="store_true", help="also write 10/25/50/75/100 %% frames")
    ap.add_argument("--check", action="store_true", help="exit non-zero if any session cannot be replayed")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    sids = ([d.name for d in sorted(config.SESSIONS_DIR.iterdir()) if (d / "metadata.json").exists()]
            if a.all else [a.session_id])
    if not sids or sids == [None]:
        ap.error("give a session_id or --all")
    bad = 0
    for sid in sids:
        try:
            rep = replay_session(sid, a.out, a.keyframes)
        except FileNotFoundError as e:
            print(f"{sid}: missing {e.filename}"); bad += 1; continue
        print(json.dumps(rep, ensure_ascii=False))
        bad += 0 if rep["replayable"] else 1
    if a.check and bad:
        print(f"{bad} session(s) not replayable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
