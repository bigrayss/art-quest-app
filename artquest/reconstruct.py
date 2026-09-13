"""Rebuild a drawing from its event + stroke log.

The stroke log alone is *not* the drawing. A child who undoes a stroke, or
clears the canvas, leaves strokes in `strokes.jsonl` that are not on the final
artwork — that is the point of an append-only log, nothing is ever rewritten.
Replaying the stroke list in order therefore paints back work the child
deliberately removed.

The unified event timeline carries the missing information: `UNDO` / `REDO` /
`CLEAR` records name the strokes they take off the canvas and put back
(`removed` / `restored`), so reconstruction walks the timeline and renders only
the strokes still visible at the end.

Sessions recorded before those payloads existed logged bare `UNDO` / `REDO` /
`CLEAR` events. For them we fall back to the semantics of the linear undo stack
the UI actually implements (undo removes the most recent visible stroke, redo
puts back what the last undo took, clear removes everything). That is exact for
every history except undo *across* a clear, which the old log cannot express.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from .logstore import read_json

# Mirrors static/app.js TOOLS: {size multiplier, pressure sensitivity}
TOOL_WIDTH = {"pencil": 1.0, "brush": 3.0, "marker": 6.0, "eraser": 6.0}
TOOL_PRESSURE = {"pencil": 0.4, "brush": 1.0, "marker": 0.0, "eraser": 0.0}

DRAW_TYPES = ("STROKE", "ERASE")
TIMELINE_TYPES = DRAW_TYPES + ("UNDO", "REDO", "CLEAR")

DEFAULT_CANVAS = (1024, 704)
# Width the replay and the saved artwork are both reduced to before comparing.
# Coarse on purpose: we are checking that the same strokes are there, not that
# PIL and the browser's canvas rasterise a line identically.
COMPARE_WIDTH = 96


# -- timeline --------------------------------------------------------------
def _ops(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Canvas-mutating events, in the order the client produced them.

    Every one of these is client-side and carries a monotonic `seq`; server-side
    records (feedback, session end) have none and are not canvas operations.
    """
    ops = [e for e in events if e.get("type") in TIMELINE_TYPES]
    if ops and all(e.get("seq") is not None for e in ops):
        ops.sort(key=lambda e: int(e["seq"]))
    return ops


def visible_ids(events: List[Dict[str, Any]]) -> Optional[List[str]]:
    """Stroke ids still on the canvas after the whole timeline, or None.

    None means the timeline carries no drawing operations at all (an old or
    truncated event log); the caller should fall back to the stroke list.
    """
    ops = _ops(events)
    if not ops:
        return None
    visible: List[str] = []
    undone: List[List[str]] = []   # legacy fallback: what each UNDO took off

    for e in ops:
        kind, p = e.get("type"), e.get("payload") or {}
        if kind in DRAW_TYPES:
            sid = p.get("stroke_id")
            if sid:
                visible.append(sid)
            undone.clear()          # a new stroke drops the redo stack
            continue

        removed, restored = p.get("removed"), p.get("restored")
        if removed is None and restored is None:        # pre-payload session
            if kind == "UNDO":
                removed, restored = visible[-1:], []
                if removed:
                    undone.append(list(removed))
            elif kind == "REDO":
                removed, restored = [], (undone.pop() if undone else [])
            else:                                       # CLEAR
                removed, restored = list(visible), []
                undone.clear()
        gone = set(removed or ())
        kept = [i for i in visible if i not in gone]
        seen = set(kept)
        # a malformed payload must not get a stroke painted twice
        visible = kept + [i for i in (restored or ()) if i and i not in seen and not seen.add(i)]
    return visible


def visible_strokes(events: List[Dict[str, Any]],
                    strokes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The strokes that survive to the final artwork, in painting order."""
    order = visible_ids(events)
    if order is None:
        return sorted(strokes, key=lambda s: int(s.get("seq") or 0))
    by_id = {s.get("stroke_id"): s for s in strokes if s.get("stroke_id")}
    return [by_id[i] for i in order if i in by_id]


def audit_streams(events: List[Dict[str, Any]],
                  strokes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cross-check the event log and the stroke log against each other.

    Exact and threshold-free, which is what makes it the check worth trusting:
    every stroke the timeline draws must exist in `strokes.jsonl` and vice
    versa, and every id an undo/redo/clear names must be a stroke that was
    actually drawn. A batch lost on upload, a duplicated id, or an undo that
    refers to nothing shows up here as a list of ids, not as a blurry number.
    """
    ops = _ops(events)
    drawn: List[str] = []
    referenced: set = set()
    for e in ops:
        p = e.get("payload") or {}
        if e.get("type") in DRAW_TYPES:
            if p.get("stroke_id"):
                drawn.append(p["stroke_id"])
        else:
            referenced.update(i for i in (p.get("removed") or ()) if i)
            referenced.update(i for i in (p.get("restored") or ()) if i)

    logged = [s.get("stroke_id") for s in strokes if s.get("stroke_id")]
    if not drawn:
        # a session recorded before events carried stroke ids: nothing to cross-check
        return {"status": "not_applicable", "drawn": 0, "logged": len(logged)}

    drawn_set, logged_set = set(drawn), set(logged)
    out = {
        "status": "ok", "drawn": len(drawn), "logged": len(logged),
        # in the timeline but never uploaded as a stroke record
        "missing_strokes": sorted(drawn_set - logged_set)[:20],
        # uploaded as a stroke but absent from the timeline
        "orphan_strokes": sorted(logged_set - drawn_set)[:20],
        "duplicate_ids": sorted({i for i in drawn if drawn.count(i) > 1})[:20],
        # undo/redo/clear naming a stroke that was never drawn
        "unknown_refs": sorted(referenced - drawn_set)[:20],
    }
    if any(out[k] for k in ("missing_strokes", "orphan_strokes", "duplicate_ids", "unknown_refs")):
        out["status"] = "mismatch"
    return out


# -- rendering -------------------------------------------------------------
def _width(stroke: Dict[str, Any], pressure: float) -> float:
    tool = stroke.get("tool", "pencil")
    mult, sens = TOOL_WIDTH.get(tool, 1.0), TOOL_PRESSURE.get(tool, 0.0)
    w = float(stroke.get("size") or 4) * mult * ((1 - sens) + sens * 2 * pressure if sens else 1)
    return max(0.5, w)


def _paint(draw: ImageDraw.ImageDraw, stroke: Dict[str, Any],
           pts: List[List[float]], color: str) -> None:
    for i in range(1, len(pts)):
        p = pts[i][3] if len(pts[i]) > 3 else 0.5
        draw.line((pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]),
                  fill=color, width=int(round(_width(stroke, p))))
    if len(pts) == 1:  # a tap still leaves a dot
        r = _width(stroke, pts[0][3] if len(pts[0]) > 3 else 0.5) / 2
        draw.ellipse((pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r), fill=color)


def render(strokes: List[Dict[str, Any]], size: Tuple[int, int], upto: int = -1) -> Image.Image:
    """Paint the given strokes onto a white canvas of `size`."""
    img = Image.new("RGBA", size, (255, 255, 255, 255))
    n = len(strokes) if upto < 0 else max(0, min(upto, len(strokes)))
    for s in strokes[:n]:
        pts = s.get("points") or []
        if not pts:
            continue
        erase = bool(s.get("erase"))
        color = "#ffffff" if erase else (s.get("color") or "#222222")
        alpha = 1.0 if erase else float(s.get("opacity") or 1.0)
        if alpha >= 0.99:
            _paint(ImageDraw.Draw(img), s, pts, color)
        else:
            # translucent tools (marker, brush) let the canvas show through
            layer = Image.new("RGBA", size, (0, 0, 0, 0))
            _paint(ImageDraw.Draw(layer), s, pts, color)
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
            img = Image.alpha_composite(img, layer)
    return img.convert("RGB")


def ink_ratio(img: Image.Image) -> float:
    """Fraction of the canvas that carries ink — a coarse completeness signal."""
    g = img.convert("L")
    hist = g.histogram()
    return sum(hist[:245]) / float(g.size[0] * g.size[1])


def compare(replay: Image.Image, final: Image.Image) -> Dict[str, Any]:
    """How far the reconstruction is from the artwork the child actually saved.

    Both images are reduced to `COMPARE_WIDTH` first, so antialiasing and the
    one-pixel width differences between PIL and the browser wash out and what
    remains is a difference in *content*.

    `rel` is the verdict: disagreeing ink over total ink, i.e. 1 - IoU measured
    on ink mass. 0 means the same drawing, 1 means the two images share no ink
    at all (a blank replay against a finished artwork). `diff` is the raw
    per-pixel mean, kept because it is easy to eyeball, but it scales with how
    much of the canvas is covered and so makes a poor threshold on its own.
    """
    box = (COMPARE_WIDTH, max(1, round(replay.height * COMPARE_WIDTH / replay.width)))
    a = replay.convert("L").resize(box, Image.BILINEAR)
    b = final.convert("L").resize(box, Image.BILINEAR)
    pa, pb = a.tobytes(), b.tobytes()   # one byte per pixel in mode "L"
    n = float(box[0] * box[1])
    absdiff = sum(abs(x - y) for x, y in zip(pa, pb))
    ink_a, ink_b = sum(255 - v for v in pa), sum(255 - v for v in pb)
    union = max(ink_a, ink_b)
    r_ink, f_ink = ink_ratio(replay), ink_ratio(final)
    return {"rel": round(absdiff / union, 4) if union else 0.0,
            "diff": round(absdiff / (255.0 * n), 4),
            "replay_ink": round(r_ink, 5),
            "final_ink": round(f_ink, 5),
            "ink_ratio": round(r_ink / f_ink, 3) if f_ink > 1e-6 else None}


# -- session-level helpers -------------------------------------------------
def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not Path(path).exists():
        return []
    import json
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:  # tolerate a torn final line
                continue
    return out


def canvas_size(meta: Dict[str, Any]) -> Tuple[int, int]:
    c = meta.get("canvas") or {}
    return (int(c.get("width") or DEFAULT_CANVAS[0]), int(c.get("height") or DEFAULT_CANVAS[1]))


def rebuild(session_dir: Path) -> Dict[str, Any]:
    """Reconstruct one session directory from its logs alone."""
    d = Path(session_dir)
    meta = read_json(d / "metadata.json") or {}
    strokes = read_jsonl(d / "strokes.jsonl")
    events = read_jsonl(d / "events.jsonl")
    vis = visible_strokes(events, strokes)
    size = canvas_size(meta)
    return {"meta": meta, "size": size, "strokes": vis,
            "image": render(vis, size),
            "audit": audit_streams(events, strokes),
            "logged": len(strokes), "visible": len(vis),
            "points": sum(len(s.get("points") or []) for s in vis)}


def check_final(session_dir: Path, built: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Reconstruct, then compare against `final.png`.

    This is the check that matters at collection time: if it fails, the logs and
    the artwork disagree and no amount of later analysis can tell which is right.
    """
    d = Path(session_dir)
    built = built or rebuild(d)
    report = {"strokes_logged": built["logged"], "strokes_visible": built["visible"],
              "strokes_removed": built["logged"] - built["visible"],
              "streams": built["audit"]}
    final = d / "final.png"
    if not final.exists():
        report["rel"] = report["diff"] = None
        return report
    with Image.open(final) as f:
        report.update(compare(built["image"], f.convert("RGB")))
    return report
