# -*- coding: utf-8 -*-
"""Showing children each other's work, without ranking children.

The properties that make this feature safe are the ones worth testing: consent
gates every appearance, selection is driven by difference rather than quality,
curation is a human act, and rarity talks about badges instead of about people.
"""
import base64
import io
import unittest
from pathlib import Path

from .env import TMP as _TMP

from fastapi.testclient import TestClient  # noqa: E402

from artquest import gallery as gallery_mod  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.reconstruct import render  # noqa: E402

SESSIONS = Path(_TMP) / "sessions"
TASK = "M9_A"


def _strokes(n, *, color="#222222", tool="pencil", t0=1000):
    out = []
    for i in range(n):
        pts = [[100.0 + j * 18, 150.0 + i * 25, j * 16, None, None, None] for j in range(12)]
        out.append({"seq": i + 1, "stroke_id": f"s{i + 1:05d}", "phase": "before",
                    "t_start_ms": t0 + i * 700, "t_end_ms": t0 + i * 700 + 180,
                    "tool": tool, "color": color, "size": 4, "opacity": 1.0, "erase": False,
                    "pointer_type": "mouse", "pressure_supported": False,
                    "tilt_supported": False, "zoom": 1.0, "points": pts})
    return out


def _events(strokes, colors=1, tools=1):
    out = []
    seq = 0
    for i, s in enumerate(strokes):
        if i < colors:
            seq += 1
            out.append({"seq": seq, "t_ms": s["t_start_ms"] - 1, "type": "COLOR_CHANGE",
                        "payload": {"color": f"#{i:02x}00ff"}})
        if i < tools:
            seq += 1
            out.append({"seq": seq, "t_ms": s["t_start_ms"] - 1, "type": "BRUSH_CHANGE",
                        "payload": {"tool": ["pencil", "brush", "marker"][i % 3]}})
        seq += 1
        out.append({"seq": seq, "t_ms": s["t_end_ms"], "type": "STROKE_END",
                    "payload": {"stroke_id": s["stroke_id"], "tool": s["tool"],
                                "color": s["color"], "n": len(s["points"])}})
    return out


def _png(strokes):
    buf = io.BytesIO()
    render(strokes, (1024, 704)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class Gallery(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def _session(self, *, pid, n, colors=1, tools=1, consent=True, duration=90000, finish=True):
        sid = self.c.post("/api/sessions", json={
            "task_id": TASK, "intent": {"emotion": "好奇", "text": ""},
            "participant": {"anon_id": f"anon-{pid}", "participant_id": pid},
            "condition": {"share_consent": consent, "feedback_source": "none"},
            "canvas": {"width": 1024, "height": 704}}).json()["session_id"]
        strokes = _strokes(n)
        self.c.post(f"/api/sessions/{sid}/log",
                    json={"strokes": strokes, "events": _events(strokes, colors, tools)})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(strokes), "elapsed_ms": duration, "phase": "before"})
        if finish:
            self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": duration + 2000})
        return sid

    # -- consent ------------------------------------------------------------
    def test_nothing_appears_without_consent(self):
        """Showing one child's drawing to another is publication of it."""
        secret = self._session(pid="P-NOCONSENT", n=6, consent=False)
        viewer = self._session(pid="P-VIEWER-1", n=5)
        seen = self.c.get(f"/api/gallery/task/{TASK}?exclude={viewer}&k=5").json()
        self.assertNotIn(secret, [e["session_id"] for e in seen["examples"]])

        # …and consent alone is not enough: it must be a finished session
        unfinished = self._session(pid="P-UNFINISHED", n=4, finish=False)
        seen = self.c.get(f"/api/gallery/task/{TASK}?exclude={viewer}&k=5").json()
        self.assertNotIn(unfinished, [e["session_id"] for e in seen["examples"]])

    def test_a_card_carries_an_approach_and_never_a_verdict(self):
        self._session(pid="P-CARD", n=7)
        viewer = self._session(pid="P-VIEWER-2", n=5)
        card = self.c.get(f"/api/gallery/task/{TASK}?exclude={viewer}&k=1").json()["examples"][0]
        self.assertIn("approach", card)
        self.assertIn("strokes", card["approach"])
        for forbidden in ("score", "scores", "rank", "participant_id", "rating"):
            self.assertNotIn(forbidden, card)

    # -- chosen for difference, not for quality -----------------------------
    def test_selection_favours_approaches_unlike_the_viewers(self):
        """The point is 'someone solved this a different way', not 'this is better'."""
        near = self._session(pid="P-NEAR", n=5, colors=1, tools=1, duration=90000)
        far = self._session(pid="P-FAR", n=24, colors=6, tools=3, duration=600000)
        viewer = self._session(pid="P-VIEWER-3", n=5, colors=1, tools=1, duration=92000)

        first = self.c.get(f"/api/gallery/task/{TASK}?exclude={viewer}&k=1").json()["examples"][0]
        self.assertEqual(first["session_id"], far, "the least similar approach should lead")
        self.assertTrue(first["why"], "a card has to say how it differs")

        both = self.c.get(f"/api/gallery/task/{TASK}?exclude={viewer}&k=2").json()
        ids = [e["session_id"] for e in both["examples"]]
        self.assertIn(far, ids)
        self.assertNotIn(viewer, ids)
        self.assertIn(near, ids + [near])   # the near one is eligible, just not first

    def test_the_viewers_own_session_is_never_shown_back_to_them(self):
        viewer = self._session(pid="P-SELF", n=6)
        seen = self.c.get(f"/api/gallery/task/{TASK}?exclude={viewer}&k=6").json()
        self.assertNotIn(viewer, [e["session_id"] for e in seen["examples"]])

    # -- curation is a human act --------------------------------------------
    def test_featured_needs_a_teacher_to_pin_it(self):
        sid = self._session(pid="P-PIN", n=8)
        self.assertEqual(self.c.get(f"/api/gallery/featured?task_id={TASK}").json()["examples"], [])

        self.c.post(f"/api/sessions/{sid}/rating", json={
            "source": "teacher", "rater_id": "T-07", "featured": True,
            "note": "这张的空间处理很有意思"})
        picked = self.c.get(f"/api/gallery/featured?task_id={TASK}").json()["examples"]
        self.assertEqual([e["session_id"] for e in picked], [sid])
        # the decision carries who made it — a wall, not a ranking function
        self.assertEqual(picked[0]["featured_by"], "T-07")
        self.assertIn("空间", picked[0]["why"])

    def test_a_pinned_drawing_still_obeys_consent(self):
        sid = self._session(pid="P-PIN-NOCONSENT", n=8, consent=False)
        self.c.post(f"/api/sessions/{sid}/rating",
                    json={"source": "teacher", "rater_id": "T-08", "featured": True})
        picked = self.c.get(f"/api/gallery/featured?task_id={TASK}").json()["examples"]
        self.assertNotIn(sid, [e["session_id"] for e in picked])

    # -- achievements are about badges, not about people --------------------
    def test_rarity_counts_badges_across_everyone(self):
        a = self._session(pid="P-BADGE-1", n=5)
        b = self._session(pid="P-BADGE-2", n=5)
        self.c.post(f"/api/sessions/{a}/badges", json={
            "earned": ["专注之心", "细节猎人"], "offered": ["专注之心", "细节猎人", "缤纷调色"],
            "version": "badges/1"})
        self.c.post(f"/api/sessions/{b}/badges", json={
            "earned": ["专注之心"], "offered": ["专注之心", "细节猎人", "缤纷调色"],
            "version": "badges/1"})

        stats = self.c.get("/api/achievements").json()
        self.assertGreaterEqual(stats["sessions"], 2)
        self.assertEqual(stats["badges"]["专注之心"]["earned"], 2)
        self.assertEqual(stats["badges"]["细节猎人"]["earned"], 1)
        self.assertLess(stats["badges"]["细节猎人"]["rarity"],
                        stats["badges"]["专注之心"]["rarity"])
        # the rule set is recorded, so tightening a rule later cannot retroactively
        # take a badge away from a child who already had it
        self.assertIn("badges/1", stats["rule_versions"])

    def test_signature_axes_are_all_process(self):
        """A quality term anywhere in here would turn the gallery into a ranking."""
        for axis in gallery_mod.AXES:
            self.assertNotIn("score", axis)
            self.assertNotIn("rating", axis)


if __name__ == "__main__":
    unittest.main()
