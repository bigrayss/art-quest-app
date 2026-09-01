"""Replay a session from `strokes.jsonl` — proof the log is the primary data.

If a drawing can be rebuilt from the stroke log alone, the log is complete;
key frames (10/25/50/75/100 %) never have to be stored, they are regenerated
on demand.

    python3 tools/replay.py <session_id> [--out DIR] [--keyframes]
    python3 tools/replay.py --all --check     # verify every session replays
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw  # noqa: E402

from artquest import config  # noqa: E402

# Mirrors static/app.js TOOLS: {size multiplier, pressure sensitivity}
TOOL_WIDTH = {"pencil": 1.0, "brush": 3.0, "marker": 6.0, "eraser": 6.0}
TOOL_PRESSURE = {"pencil": 0.4, "brush": 1.0, "marker": 0.0, "eraser": 0.0}
KEYFRAME_PCTS = (10, 25, 50, 75, 100)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def canvas_size(meta: Dict[str, Any]) -> Tuple[int, int]:
    c = meta.get("canvas") or {}
    return int(c.get("width") or 1024), int(c.get("height") or 704)


def _width(stroke: Dict[str, Any], pressure: float) -> float:
    tool = stroke.get("tool", "pencil")
    mult, sens = TOOL_WIDTH.get(tool, 1.0), TOOL_PRESSURE.get(tool, 0.0)
    w = float(stroke.get("size") or 4) * mult * ((1 - sens) + sens * 2 * pressure if sens else 1)
    return max(0.5, w)


def render(strokes: List[Dict[str, Any]], size: Tuple[int, int], upto: int = -1) -> Image.Image:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for s in strokes[:upto if upto >= 0 else len(strokes)]:
        pts = s.get("points") or []
        color = "#ffffff" if s.get("erase") else (s.get("color") or "#222222")
        for i in range(1, len(pts)):
            x0, y0 = pts[i - 1][0], pts[i - 1][1]
            x1, y1, p = pts[i][0], pts[i][1], (pts[i][3] if len(pts[i]) > 3 else 0.5)
            d.line((x0, y0, x1, y1), fill=color, width=int(round(_width(s, p))))
        if len(pts) == 1:  # a tap still leaves a dot
            r = _width(s, pts[0][3] if len(pts[0]) > 3 else 0.5) / 2
            d.ellipse((pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r), fill=color)
    return img


def ink_ratio(img: Image.Image) -> float:
    g = img.convert("L")
    return sum(1 for v in g.getdata() if v < 245) / float(g.size[0] * g.size[1])


def replay_session(sid: str, out_dir: Path = None, keyframes: bool = False) -> Dict[str, Any]:
    d = config.SESSIONS_DIR / sid
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    strokes = read_jsonl(d / "strokes.jsonl")
    size = canvas_size(meta)
    out = out_dir or (d / "replay")
    out.mkdir(parents=True, exist_ok=True)

    full = render(strokes, size)
    full.save(out / "replay.png")
    frames = []
    if keyframes and strokes:
        for pct in KEYFRAME_PCTS:
            n = max(1, round(len(strokes) * pct / 100))
            render(strokes, size, n).save(out / f"keyframe_{pct:03d}.png")
            frames.append(pct)

    report = {
        "session_id": sid, "strokes": len(strokes),
        "points": sum(len(s.get("points") or []) for s in strokes),
        "canvas": list(size), "keyframes": frames,
        "replay_ink": round(ink_ratio(full), 5),
    }
    final = d / "final.png"
    if final.exists():
        report["final_ink"] = round(ink_ratio(Image.open(final).convert("RGB")), 5)
        denom = max(report["final_ink"], 1e-6)
        report["ink_ratio"] = round(report["replay_ink"] / denom, 3)
        # the canvas and PIL rasterise differently; this is a completeness signal,
        # not a pixel-exact match
        report["replayable"] = bool(strokes) and 0.4 <= report["ink_ratio"] <= 2.5
    else:
        report["replayable"] = bool(strokes)
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
