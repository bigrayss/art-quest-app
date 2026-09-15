# -*- coding: utf-8 -*-
"""Showing children each other's work — without ranking children.

The obvious version of this feature is a leaderboard of "best" drawings. This
module deliberately does not build that, for three reasons that are not
squeamishness:

1. **Ranking undoes the rest of the design.** Everywhere else this app refuses
   to hand a child a verdict: N/A is not a low score, badges read process and
   not quality, the end of a task says what it *trained*. A "best works" board
   is that verdict, just delivered socially instead of numerically.
2. **It is publication of a minor's work.** Showing one child's drawing to
   another is exactly what parental consent covers (`docs/ETHICS.md`), so
   nothing here appears without `share_consent` frozen into that session.
3. **It contaminates the study.** A child who has seen other solutions before
   drawing is no longer a clean observation of the task condition. So the
   gallery is a recorded condition, off by default, and when on it is only
   reachable *after* the child has submitted their own work.

What it offers instead:

* `diverse_examples` — other people's *approaches* to the same task, chosen for
  how much they differ from yours rather than how good they are. "Someone else
  solved this a completely different way" is the thing a young artist actually
  learns from, and it needs no judgement of anybody.
* `featured_examples` — work a teacher chose to show. A human decision with a
  name attached to it, which is what pinning a drawing on the classroom wall
  has always been, and is defensible where an algorithm ranking children is not.
* `achievement_stats` — how rare each badge is across everyone. Collection and
  rarity carry the game feeling without comparing one child's art to another's.
"""
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import events as ev
from .history import _process_from_events, iter_sessions
from .storage import session_labels

# Signature axes: all process, none of them a judgement of the drawing.
AXES = ("strokes", "colors", "tools", "duration", "undo", "zoom", "pause_share")


def is_shareable(meta: Dict[str, Any]) -> bool:
    """Consent is per session and frozen, never inferred or defaulted to yes."""
    return bool((meta.get("condition") or {}).get("share_consent")) and meta.get("status") == "done"


def signature(meta: Dict[str, Any]) -> Dict[str, float]:
    """How this drawing was *made*, as a handful of comparable numbers."""
    sid = meta.get("id") or meta.get("session_id")
    proc = _process_from_events(sid)
    duration = ((meta.get("times") or {}).get("duration_ms")) or 0
    strokes = proc["strokes"] or 1
    return {
        # log-scaled: 10 strokes vs 20 is a real difference, 200 vs 210 is not
        "strokes": math.log1p(proc["strokes"]),
        "colors": float(proc["n_colors"]),
        "tools": float(proc["n_tools"]),
        "duration": math.log1p(duration / 1000.0),
        "undo": proc["undo"] / strokes,
        "zoom": 1.0 if proc["zoom_gestures"] else 0.0,
        "pause_share": (proc["pause_ms"] / duration) if duration else 0.0,
    }


def _normalize(rows: Sequence[Dict[str, float]]) -> List[List[float]]:
    if not rows:
        return []
    out = []
    lo = {a: min(r.get(a, 0.0) for r in rows) for a in AXES}
    hi = {a: max(r.get(a, 0.0) for r in rows) for a in AXES}
    for r in rows:
        out.append([0.0 if hi[a] - lo[a] < 1e-9 else (r.get(a, 0.0) - lo[a]) / (hi[a] - lo[a])
                    for a in AXES])
    return out


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _card(meta: Dict[str, Any], sig: Dict[str, float], *, why: str = "") -> Dict[str, Any]:
    """What a viewer is shown. No score, no name, no ranking."""
    sid = meta.get("id")
    proc = _process_from_events(sid)
    return {
        "session_id": sid,
        "task_id": meta.get("quest_id"),
        "family": (meta.get("task") or {}).get("family", ""),
        "image": f"/files/{sid}/final.png",
        "created_at": meta.get("created_at"),
        # the approach, in the viewer's language — never "this one is better"
        "approach": {
            "strokes": proc["strokes"], "colors": proc["n_colors"],
            "tools": sorted(proc["tools"]), "minutes": round(((meta.get("times") or {}).get("duration_ms") or 0) / 60000, 1),
            "zoomed": bool(proc["zoom_gestures"]), "undo": proc["undo"],
        },
        "why": why,
    }


_CONTRASTS = [
    ("colors", "用的颜色比你多", "用的颜色比你少"),
    ("tools", "用的工具比你多", "只用了更少的工具"),
    ("strokes", "笔画比你多得多", "用更少的笔画就画完了"),
    ("duration", "花的时间比你长", "画得比你快"),
    ("pause_share", "停下来想的时间更多", "几乎没有停下来"),
    ("undo", "改了很多次", "几乎没有回头改"),
    ("zoom", "放大了画细节", "一直看着整张画"),
]


def _contrast(mine: Optional[Dict[str, float]], theirs: Dict[str, float],
              used: Optional[set] = None) -> Tuple[str, str]:
    """One plain sentence about how this approach differs from the viewer's.

    Each card claims a *different* axis where it can. Three cards all saying
    "took longer than you" is technically true and useless — the whole point is
    to show that there is more than one way through the task.
    """
    if not mine:
        return "另一种做法", ""
    used = used or set()
    ranked = sorted(
        ((axis, more, less, theirs.get(axis, 0.0) - mine.get(axis, 0.0))
         for axis, more, less in _CONTRASTS),
        key=lambda r: -abs(r[3]))
    fallback = None
    for axis, more, less, d in ranked:
        if abs(d) < 1e-9:
            continue
        text = more if d > 0 else less
        if fallback is None:
            fallback = (text, axis)
        if axis not in used:
            return text, axis
    return fallback or ("换了一种完全不同的做法", "")


def diverse_examples(task_id: str, *, exclude_session: str = "", k: int = 3,
                     viewer_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Other approaches to the same task, chosen for difference, not quality.

    Farthest-point selection over the process signature: the first pick is the
    approach least like the viewer's, and each next pick is the one least like
    everything already shown. Nobody is ranked; the set is chosen to span the
    space of ways people solved this.
    """
    pool: List[Tuple[Dict[str, Any], Dict[str, float]]] = []
    for meta in iter_sessions():
        if meta.get("quest_id") != task_id or meta.get("id") == exclude_session:
            continue
        if not is_shareable(meta):
            continue
        pool.append((meta, signature(meta)))
    if not pool:
        return {"task_id": task_id, "examples": [], "pool": 0}

    mine = signature(viewer_meta) if viewer_meta else None
    rows = [sig for _, sig in pool] + ([mine] if mine else [])
    vecs = _normalize(rows)
    mine_vec = vecs[-1] if mine else None
    cand = vecs[:len(pool)]

    chosen: List[int] = []
    while len(chosen) < min(k, len(pool)):
        best_i, best_d = None, -1.0
        for i in range(len(pool)):
            if i in chosen:
                continue
            refs = [cand[j] for j in chosen] + ([mine_vec] if mine_vec is not None else [])
            d = min((_dist(cand[i], r) for r in refs), default=1.0)
            if d > best_d:
                best_i, best_d = i, d
        chosen.append(best_i)

    out, used = [], set()
    for i in chosen:
        meta, sig = pool[i]
        why, axis = _contrast(mine, sig, used)
        if axis:
            used.add(axis)
        out.append(_card(meta, sig, why=why))
    return {"task_id": task_id, "examples": out, "pool": len(pool)}


def featured_examples(task_id: str = "", k: int = 8) -> Dict[str, Any]:
    """Work a teacher chose to show, newest first.

    Curation is a human act with a rater id behind it — the classroom wall, not
    a ranking function.
    """
    out = []
    for meta in iter_sessions():
        if task_id and meta.get("quest_id") != task_id:
            continue
        if not is_shareable(meta):
            continue
        picks = [r for r in _ratings(meta) if r.get("featured")]
        if picks:
            card = _card(meta, signature(meta), why=picks[-1].get("note", ""))
            card["featured_by"] = picks[-1].get("rater_id", "")
            card["featured_at"] = picks[-1].get("ts")
            out.append(card)
    out.sort(key=lambda c: c.get("featured_at") or "", reverse=True)
    return {"task_id": task_id, "examples": out[:k]}


def _ratings(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    from .reconstruct import read_jsonl
    from . import config
    sid = meta.get("id")
    return session_labels(config.SESSIONS_DIR / str(sid), "rating") if sid else []


def achievement_stats() -> Dict[str, Any]:
    """How rare each badge is across every finished session.

    Rarity is the game mechanic that needs no artwork and no comparison between
    children: "8 % of people have lit this one" is about the badge, not about you.
    Badges are reported by the client at the end of a session and stored with the
    rule-set version they were earned under, so tightening a rule later does not
    retroactively take a badge away.
    """
    total = 0
    counts: Dict[str, int] = {}
    versions: Dict[str, int] = {}
    for meta in iter_sessions():
        if meta.get("status") != "done":
            continue
        earned = meta.get("badges") or {}
        names = earned.get("earned") or []
        total += 1
        for name in names:
            counts[name] = counts.get(name, 0) + 1
        v = earned.get("version")
        if v:
            versions[v] = versions.get(v, 0) + 1
    stats = {name: {"earned": n, "rarity": round(n / total, 4) if total else None}
             for name, n in sorted(counts.items(), key=lambda kv: kv[1])}
    return {"sessions": total, "badges": stats, "rule_versions": versions}
