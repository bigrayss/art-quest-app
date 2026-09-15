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

from PIL import Image, ImageChops, ImageColor, ImageDraw

from . import events as ev
from .logstore import read_json, read_jsonl as _read_jsonl
from .storage import session_task

# Mirrors static/app.js TOOLS: {size multiplier, pressure sensitivity}
TOOL_WIDTH = {"pencil": 1.0, "brush": 3.0, "marker": 6.0, "eraser": 6.0}
TOOL_PRESSURE = {"pencil": 0.4, "brush": 1.0, "marker": 0.0, "eraser": 0.0}
# Also mirrors static/app.js TOOLS. At 4 px a pencil's caps and joins are a
# rounding error; a 24 px marker's are most of its silhouette, which is why
# marker-heavy sessions used to miss the replay check on geometry alone.
TOOL_CAP = {"pencil": "round", "brush": "round", "marker": "square", "eraser": "round"}

DRAW_TYPES = ev.DRAW_TYPES                      # STROKE_END / ERASE, old name folded in
TIMELINE_TYPES = DRAW_TYPES + (ev.UNDO, ev.REDO, ev.CLEAR)

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
    ops = [e for e in events if ev.canonical(e.get("type")) in TIMELINE_TYPES]
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
        kind, p = ev.canonical(e.get("type")), e.get("payload") or {}
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
        if ev.canonical(e.get("type")) in DRAW_TYPES:
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


# -- the initial canvas ------------------------------------------------------
# Replay is `initial canvas + stroke stream + events`. For a family like M3 the
# initial canvas is not blank: incomplete figures are printed on it, and the
# child draws over them. They are stored as vector primitives in canvas space
# (not a bitmap) so this renderer and `static/app.js` produce the identical
# starting image — otherwise every fragment session would fail `replay_matches_final`.
def draw_stimulus(img: Image.Image, stimulus: Optional[Dict[str, Any]]) -> Image.Image:
    if not stimulus or stimulus.get("kind") != "fragments":
        return img
    d = ImageDraw.Draw(img)
    color, w = stimulus.get("stroke", "#3a3a3a"), int(stimulus.get("width", 3))
    for it in stimulus.get("items") or []:
        kind = it.get("type")
        if kind == "dot":
            r = it["r"]
            d.ellipse((it["x"] - r, it["y"] - r, it["x"] + r, it["y"] + r), fill=color)
        elif kind == "line":
            d.line((it["x1"], it["y1"], it["x2"], it["y2"]), fill=color, width=w)
        elif kind == "arc":
            cx, cy, r = it["cx"], it["cy"], it["r"]
            d.arc((cx - r, cy - r, cx + r, cy + r), it["a0"], it["a1"], fill=color, width=w)
        elif kind == "corner":
            x, y, ww, hh = it["x"], it["y"], it["w"], it["h"]
            d.line((x, y, x, y + hh), fill=color, width=w)
            d.line((x, y + hh, x + ww, y + hh), fill=color, width=w)
        elif kind == "curve":
            pts = []
            for i in range(33):                     # quadratic bezier, sampled
                t = i / 32.0
                u = 1 - t
                pts.append((u * u * it["x1"] + 2 * u * t * it["cx"] + t * t * it["x2"],
                            u * u * it["y1"] + 2 * u * t * it["cy"] + t * t * it["y2"]))
            d.line(pts, fill=color, width=w, joint="curve")
        elif kind == "rect_open":
            x, y, ww, hh, gap = it["x"], it["y"], it["w"], it["h"], it.get("gap", "top")
            sides = {"top": (x, y, x + ww, y), "right": (x + ww, y, x + ww, y + hh),
                     "bottom": (x, y + hh, x + ww, y + hh), "left": (x, y, x, y + hh)}
            for name, seg in sides.items():
                if name != gap:
                    d.line(seg, fill=color, width=w)
    return img


# -- rendering -------------------------------------------------------------
def _width(stroke: Dict[str, Any], pressure: float) -> float:
    tool = stroke.get("tool", "pencil")
    mult, sens = TOOL_WIDTH.get(tool, 1.0), TOOL_PRESSURE.get(tool, 0.0)
    w = float(stroke.get("size") or 4) * mult * ((1 - sens) + sens * 2 * pressure if sens else 1)
    return max(0.5, w)


# A device that does not measure pressure logs `None`. The renderer still needs
# a width, so it falls back to the neutral half — the *log* stays honest, the
# picture does not pretend the fallback was a reading.
NEUTRAL_PRESSURE = 0.5


def _pressure(point: List[Any]) -> float:
    v = point[3] if len(point) > 3 else None
    return float(v) if isinstance(v, (int, float)) else NEUTRAL_PRESSURE


def _extend(pts: List[List[Any]], w: float) -> Tuple[List[float], List[float]]:
    """A square cap juts half a width past each end; a round one does not."""
    (ax, ay), (bx, by) = (pts[0][0], pts[0][1]), (pts[1][0], pts[1][1])
    dx, dy = ax - bx, ay - by
    n = (dx * dx + dy * dy) ** 0.5 or 1.0
    head = [ax + dx / n * w / 2, ay + dy / n * w / 2]
    (cx, cy), (dx2, dy2) = (pts[-1][0], pts[-1][1]), (pts[-2][0], pts[-2][1])
    ex, ey = cx - dx2, cy - dy2
    m = (ex * ex + ey * ey) ** 0.5 or 1.0
    tail = [cx + ex / m * w / 2, cy + ey / m * w / 2]
    return head, tail


def _segments(stroke: Dict[str, Any], pts: List[List[Any]]):
    """Segments and joint circles, the way a canvas actually lays a stroke down."""
    cap = TOOL_CAP.get(stroke.get("tool", "pencil"), "round")
    path = [list(p) for p in pts]
    if len(path) > 1 and cap == "square":
        w0 = max(1.0, _width(stroke, _pressure(path[1])))
        head, tail = _extend(path, w0)
        path = [head] + path + [tail]
    segs, joints = [], []
    for i in range(1, len(path)):
        w = max(1, int(round(_width(stroke, _pressure(path[i])))))
        segs.append((path[i - 1][0], path[i - 1][1], path[i][0], path[i][1], w))
        # round joins: without them a wide stroke is notched at every turn
        if w > 3:
            joints.append((path[i][0], path[i][1], w / 2.0))
    if segs and segs[0][4] > 3:
        joints.append((path[0][0], path[0][1], segs[0][4] / 2.0))
    return segs, joints


def _paint(draw: ImageDraw.ImageDraw, stroke: Dict[str, Any],
           pts: List[List[Any]], color: str) -> None:
    if len(pts) == 1:  # a tap still leaves a dot
        r = _width(stroke, _pressure(pts[0])) / 2
        draw.ellipse((pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r), fill=color)
        return
    segs, joints = _segments(stroke, pts)
    for x0, y0, x1, y1, w in segs:
        draw.line((x0, y0, x1, y1), fill=color, width=w)
    for cx, cy, r in joints:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)


def _translucent_alpha(stroke: Dict[str, Any], pts: List[List[Any]],
                       size: Tuple[int, int], alpha: float) -> Image.Image:
    """The alpha map a translucent stroke actually leaves on a canvas.

    The browser sets `globalAlpha` and strokes each segment separately, so
    overlapping segments *within one stroke* darken each other — a marker drawn
    as a dense polyline is far darker than one pass of its colour. Painting the
    whole stroke once and compositing once misses that, which is what pushed
    marker-heavy sessions past the QC replay threshold.

    Composited exactly instead: a transmittance buffer multiplied by (1-alpha)
    wherever a segment lands gives `1-(1-alpha)^k` for k overlaps, which is what
    k separate composites produce. Per-segment work stays cheap by touching only
    each segment's bounding box.
    """
    W, H = size
    keep = int(round((1.0 - alpha) * 255))
    trans = Image.new("L", size, 255)

    def stamp(shape):
        x0, y0, x1, y1, w, kind = shape
        pad = int(w) // 2 + 2
        bx0, by0 = max(0, int(min(x0, x1)) - pad), max(0, int(min(y0, y1)) - pad)
        bx1, by1 = min(W, int(max(x0, x1)) + pad + 1), min(H, int(max(y0, y1)) + pad + 1)
        if bx1 <= bx0 or by1 <= by0:
            return
        box = (bx0, by0, bx1, by1)
        tile = Image.new("L", (bx1 - bx0, by1 - by0), 255)
        d = ImageDraw.Draw(tile)
        if kind == "line":
            d.line((x0 - bx0, y0 - by0, x1 - bx0, y1 - by0), fill=keep, width=int(w))
        else:
            r = w / 2.0
            d.ellipse((x0 - r - bx0, y0 - r - by0, x0 + r - bx0, y0 + r - by0), fill=keep)
        trans.paste(ImageChops.multiply(trans.crop(box), tile), box)

    if len(pts) == 1:
        w = _width(stroke, _pressure(pts[0]))
        stamp((pts[0][0], pts[0][1], pts[0][0], pts[0][1], w, "dot"))
        return ImageChops.invert(trans)
    segs, joints = _segments(stroke, pts)
    for x0, y0, x1, y1, w in segs:
        stamp((x0, y0, x1, y1, w, "line"))
    for cx, cy, r in joints:
        stamp((cx, cy, cx, cy, r * 2, "dot"))
    return ImageChops.invert(trans)


def render(strokes: List[Dict[str, Any]], size: Tuple[int, int], upto: int = -1,
           stimulus: Optional[Dict[str, Any]] = None) -> Image.Image:
    """Paint the given strokes onto the task's initial canvas."""
    # The starting canvas, kept: the eraser lifts the child's marks back to it
    # rather than to white, mirroring static/app.js — otherwise a session that
    # erased over a printed fragment would replay with the fragment gone.
    base = Image.new("RGBA", size, (255, 255, 255, 255))
    draw_stimulus(base, stimulus)
    img = base.copy()
    n = len(strokes) if upto < 0 else max(0, min(upto, len(strokes)))
    for s in strokes[:n]:
        pts = s.get("points") or []
        if not pts:
            continue
        if s.get("op") == "erase" or s.get("erase"):
            img.paste(base, (0, 0), _translucent_alpha(s, pts, size, 1.0))
            continue
        color = s.get("color") or "#222222"
        alpha = float(s.get("opacity") or 1.0)
        if alpha >= 0.99:
            _paint(ImageDraw.Draw(img), s, pts, color)
        else:
            # translucent tools (marker, brush) let the canvas show through, and
            # overlap with themselves the way the canvas composites them
            layer = Image.new("RGBA", size, ImageColor.getrgb(color) + (0,))
            layer.putalpha(_translucent_alpha(s, pts, size, alpha))
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
    """Kept as a name others import; the reading itself lives in `logstore`,
    which also knows about the gzipped form of a finished stream."""
    return _read_jsonl(path)


def canvas_size(meta: Dict[str, Any]) -> Tuple[int, int]:
    c = meta.get("canvas") or {}
    return (int(c.get("width") or DEFAULT_CANVAS[0]), int(c.get("height") or DEFAULT_CANVAS[1]))


def boundaries(events: List[Dict[str, Any]],
               strokes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Named cut points in the drawing: around each feedback and the revision.

    Percentage key frames say how far along the child was; these say *where the
    intervention was*. "What the artwork looked like when the feedback appeared"
    and "what it looked like after" is the pair a feedback experiment compares,
    and it cannot be recovered from 25/50/75 %.
    """
    ordered = sorted(strokes, key=ev.stroke_start_ms)

    def upto(t_ms: Optional[int]) -> int:
        if t_ms is None:
            return len(ordered)
        return sum(1 for s in ordered if ev.stroke_start_ms(s) < t_ms)

    shown = sorted((e.get("t_ms") or 0) for e in events
                   if ev.canonical(e.get("type")) == ev.FEEDBACK_SHOW)
    revision = next((e.get("t_ms") or 0) for e in events
                    if ev.canonical(e.get("type")) == ev.REVISION_START) \
        if any(ev.canonical(e.get("type")) == ev.REVISION_START for e in events) else None

    out: List[Dict[str, Any]] = []
    for i, t in enumerate(shown):
        suffix = "" if i == 0 else f"_{i + 1}"
        nxt = shown[i + 1] if i + 1 < len(shown) else None
        out.append({"name": f"before_feedback{suffix}", "t_ms": t, "n_strokes": upto(t)})
        out.append({"name": f"after_feedback{suffix}", "t_ms": nxt, "n_strokes": upto(nxt)})
    if revision is not None:
        out.append({"name": "before_revision", "t_ms": revision, "n_strokes": upto(revision)})
        out.append({"name": "after_revision", "t_ms": None, "n_strokes": len(ordered)})
    return out


def rebuild(session_dir: Path) -> Dict[str, Any]:
    """Reconstruct one session directory from its logs alone."""
    d = Path(session_dir)
    meta = read_json(d / "metadata.json") or {}
    strokes = read_jsonl(d / "strokes.jsonl")
    events = read_jsonl(d / "events.jsonl")
    vis = visible_strokes(events, strokes)
    size = canvas_size(meta)
    # the frozen condition is what says whether the canvas started blank
    stimulus = (session_task(d) or {}).get("stimulus") or None
    return {"meta": meta, "size": size, "strokes": vis, "stimulus": stimulus,
            "boundaries": boundaries(events, vis),
            "image": render(vis, size, stimulus=stimulus),
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
