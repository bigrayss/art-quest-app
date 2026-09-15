# -*- coding: utf-8 -*-
"""Emit our sessions in the shapes the sketch-dataset literature already reads.

Our own on-disk format is a superset of what these datasets carry, which is the
right call for collection — but a format nobody else can load is a format nobody
else will use. So the raw logs stay as they are and this converts them, per
session, into the conventional shapes:

    differsketching   the schema used by DifferSketching (SIGGRAPH Asia 2022),
                      verified field-for-field against the sample JSON in the
                      authors' repository
    quickdraw         Google QuickDraw's ndjson, the most widely consumed sketch
                      format — `drawing: [[[x…],[y…],[t…]], …]`
    svg               plain vector, openable by anything

What the conventional shapes cannot hold is listed in `LOSSY`, and every
converted file carries an `artquest` block naming what was dropped, so nobody
later mistakes the converted view for the whole record.

    python3 tools/export_sketches.py --out sketches/ --format differsketching
    python3 tools/export_sketches.py --out sketches/ --format all
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artquest import config  # noqa: E402
from artquest import events as ev  # noqa: E402
from artquest.logstore import JsonlLog  # noqa: E402
from artquest.reconstruct import visible_strokes  # noqa: E402
from artquest.storage import session_events, session_meta, session_strokes, sid_of  # noqa: E402
from artquest.logstore import read_json  # noqa: E402

SCHEMA_NOTE = "artquest/1 — converted view; the full record is the session directory"

# Process signal our format keeps and these interchange shapes have nowhere to put.
LOSSY = {
    "differsketching": ["per-point timestamps (only s_time/e_time survive)", "tilt",
                        "colour", "tool identity", "zoom/pan", "reference use",
                        "pauses", "which strokes each undo removed"],
    "quickdraw": ["pressure", "tilt", "colour", "stroke width", "tool identity",
                  "zoom/pan", "reference use", "pauses", "undo detail"],
    "svg": ["all timing", "pressure", "tilt", "everything about the process"],
}


def _epoch_ms(meta: Dict[str, Any]) -> int:
    t = ((meta.get("times") or {}).get("started_at")) or ""
    try:
        return int(datetime.fromisoformat(t).timestamp() * 1000)
    except ValueError:
        return 0


def _load(sid: str):
    d = config.SESSIONS_DIR / sid
    meta = session_meta(d)
    events = session_events(d)
    strokes = session_strokes(d)
    # only what is on the finished artwork, in painting order
    return meta, events, visible_strokes(events, strokes)


def _provenance(meta: Dict[str, Any], fmt: str) -> Dict[str, Any]:
    task = meta.get("task") or {}
    return {
        "schema": SCHEMA_NOTE,
        "session_id": sid_of(meta),
        "task_id": meta.get("quest_id"),
        "family": task.get("family", ""),
        "form_id": task.get("form_id", ""),
        "prompt_style": task.get("prompt_style", ""),
        "canvas": meta.get("canvas"),
        "condition": meta.get("condition"),
        "dropped_in_this_format": LOSSY.get(fmt, []),
    }


# -- DifferSketching ---------------------------------------------------------
def to_differsketching(sid: str) -> Optional[Dict[str, Any]]:
    """Their schema exactly: strokes[{id, draw_type, path, use_pressure,
    pressure, s_time, e_time, width}], plus undo_count and rm_stroke_count.

    `path` is [[x, y], …] and `pressure` is a parallel array, so the interleaved
    point tuples we log are split apart here. They record no per-point time, so
    ours is narrowed to the stroke's start and end.
    """
    meta, events, strokes = _load(sid)
    if not strokes:
        return None
    base = _epoch_ms(meta)
    tools = sorted({s.get("tool") for s in strokes if s.get("tool")})
    out_strokes = []
    for i, s in enumerate(strokes):
        pts = s.get("points") or []
        supported = bool(s.get("pressure_supported"))
        out_strokes.append({
            "id": i,
            # they use draw_type for their capture conditions; ours is the tool,
            # indexed so the field stays an int as their loaders expect
            "draw_type": tools.index(s.get("tool")) if s.get("tool") in tools else 0,
            "path": [[round(p[0], 1), round(p[1], 1)] for p in pts],
            "use_pressure": supported,
            # an unmeasured channel stays empty rather than becoming zeros
            "pressure": [p[3] for p in pts] if supported else [],
            "s_time": base + int(s.get("t_start_ms") or 0),
            "e_time": base + int(s.get("t_end_ms") or 0),
            "width": s.get("size") or 1,
        })
    kinds = [ev.canonical(e.get("type")) for e in events]
    all_strokes = session_strokes(config.SESSIONS_DIR / sid)
    return {
        "strokes": out_strokes,
        "undo_count": kinds.count(ev.UNDO),
        "rm_stroke_count": len(all_strokes) - len(strokes),
        "artquest": dict(_provenance(meta, "differsketching"),
                         tool_by_draw_type={i: t for i, t in enumerate(tools)}),
    }


# -- QuickDraw ---------------------------------------------------------------
def to_quickdraw(sid: str) -> Optional[Dict[str, Any]]:
    """`drawing: [[[x…], [y…], [t…]], …]` — the raw QuickDraw layout, with `t`
    in milliseconds from the start of the session."""
    meta, _events, strokes = _load(sid)
    if not strokes:
        return None
    drawing = []
    for s in strokes:
        pts = s.get("points") or []
        t0 = int(s.get("t_start_ms") or 0)
        drawing.append([[round(p[0]) for p in pts],
                        [round(p[1]) for p in pts],
                        [t0 + int(p[2] or 0) for p in pts]])
    return {
        "key_id": sid_of(meta),
        "word": meta.get("quest_id"),          # the task, in their "category" slot
        "recognized": None,                    # no recognition step in this study
        "timestamp": (meta.get("times") or {}).get("started_at"),
        "countrycode": "",
        "drawing": drawing,
        "artquest": _provenance(meta, "quickdraw"),
    }


# -- SVG ---------------------------------------------------------------------
def to_svg(sid: str) -> Optional[str]:
    meta, _events, strokes = _load(sid)
    if not strokes:
        return None
    c = meta.get("canvas") or {}
    w, h = int(c.get("width") or 1024), int(c.get("height") or 704)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
             f'viewBox="0 0 {w} {h}">',
             f'<metadata>{json.dumps(_provenance(meta, "svg"), ensure_ascii=False)}</metadata>',
             f'<rect width="{w}" height="{h}" fill="#ffffff"/>']
    for s in strokes:
        pts = s.get("points") or []
        if not pts:
            continue
        d = "M " + " L ".join(f"{round(p[0], 1)},{round(p[1], 1)}" for p in pts)
        stroke = "#ffffff" if s.get("op") == "erase" else (s.get("color") or "#222222")
        parts.append(f'<path d="{d}" fill="none" stroke="{stroke}" '
                     f'stroke-width="{s.get("size") or 1}" stroke-linecap="round" '
                     f'stroke-linejoin="round" opacity="{s.get("opacity", 1)}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


WRITERS = {
    "differsketching": ("json", to_differsketching),
    "quickdraw": ("ndjson", to_quickdraw),
    "svg": ("svg", to_svg),
}


def export(out: Path, formats: List[str]) -> Dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    sids = [d.name for d in sorted(config.SESSIONS_DIR.iterdir())
            if JsonlLog(d / "strokes.jsonl").exists()]
    counts = {f: 0 for f in formats}
    nd = {}
    for fmt in formats:
        kind, _ = WRITERS[fmt]
        (out / fmt).mkdir(exist_ok=True) if kind != "ndjson" else None
        if kind == "ndjson":
            nd[fmt] = (out / f"{fmt}.ndjson").open("w", encoding="utf-8")
    try:
        for sid in sids:
            for fmt in formats:
                kind, fn = WRITERS[fmt]
                data = fn(sid)
                if data is None:
                    continue
                if kind == "ndjson":
                    nd[fmt].write(json.dumps(data, ensure_ascii=False) + "\n")
                elif kind == "json":
                    (out / fmt / f"{sid}.json").write_text(
                        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                else:
                    (out / fmt / f"{sid}.svg").write_text(data, encoding="utf-8")
                counts[fmt] += 1
    finally:
        for fh in nd.values():
            fh.close()
    (out / "README.txt").write_text(
        "Converted views of ArtQuest sessions.\n\n"
        "These are NOT the full record — the session directories are. Each file's\n"
        "`artquest` block lists what the format could not carry.\n\n"
        + "\n".join(f"{f}: drops {', '.join(LOSSY[f])}" for f in formats) + "\n",
        encoding="utf-8")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--format", default="all",
                    choices=list(WRITERS) + ["all"], nargs="*")
    a = ap.parse_args()
    fmts = list(WRITERS) if ("all" in a.format or a.format == "all") else list(a.format)
    counts = export(a.out, fmts)
    for k, v in counts.items():
        print(f"{k:16} {v}")
    print(f"→ {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
