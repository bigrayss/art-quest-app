"""feedback content + timestamp + source + target region + subsequent revision.

The first four are fields someone writes down. The fifth is not: it exists only
as a relation between a feedback record and the strokes that came after it, and
it is only computable if the region is in the same coordinate space as the
strokes. These tests check the whole chain, including the part that would
silently produce nonsense if the region were stored as fractions.
"""
import base64
import io
import tempfile
import unittest
from pathlib import Path

from .env import TMP as _TMP  # offline backends, throwaway data dir

from fastapi.testclient import TestClient  # noqa: E402

from artquest.main import app  # noqa: E402
from artquest.reconstruct import read_jsonl, render  # noqa: E402
from artquest.storage import session_feedback, session_labels  # noqa: E402
from tools.export_dataset import export  # noqa: E402

SESSIONS = Path(_TMP) / "sessions"
# the feedback points here; strokes are placed inside or outside it on purpose
REGION = {"shape": "rect", "coords": [600, 400, 300, 250], "label": "右下角"}


def _stroke(i, x, y, *, t_start, phase="before"):
    pts = [[float(x + j * 8), float(y + j * 4), j * 16, 0.5, 0, 0] for j in range(10)]
    return {"seq": i, "stroke_id": f"s{i:05d}", "phase": phase,
            "t_start_ms": t_start, "t_end_ms": t_start + 160, "tool": "pencil",
            "color": "#222222", "size": 4, "opacity": 1.0, "erase": False,
            "pointer_type": "mouse", "zoom": 1.0, "points": pts}


def _events(strokes):
    return [{"seq": i + 1, "t_ms": s["t_start_ms"], "type": "STROKE",
             "payload": {"stroke_id": s["stroke_id"], "tool": s["tool"], "color": s["color"],
                         "size": s["size"], "n": len(s["points"])}}
            for i, s in enumerate(strokes)]


def _png(strokes):
    buf = io.BytesIO()
    render(strokes, (1024, 704)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class FeedbackAndRevision(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def _session(self):
        r = self.c.post("/api/sessions", json={
            "quest_id": "emotion_alone", "intent": {"emotion": "平静", "text": "反馈链路"},
            "participant": {"anon_id": "anon-fb", "participant_id": "P-FB"},
            "canvas": {"width": 1024, "height": 704}})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["session_id"]

    def _drew_then_feedback_then_revised(self, *, after_in_region=3, after_outside=1):
        """Draw away from the region, get targeted feedback, then work inside it."""
        sid = self._session()
        before = [_stroke(i + 1, 100 + i * 40, 100, t_start=1000 + i * 500) for i in range(4)]
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": before, "events": _events(before)})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(before), "elapsed_ms": 60000, "phase": "before"})

        fb = self.c.post(f"/api/sessions/{sid}/feedback", json={
            "source": "teacher", "feedback_type": "targeted", "t_ms": 61000, "phase": "before",
            "text": "右下角这块还是空的，可以让它也有点内容", "target_region": REGION}).json()["feedback"]

        n = len(before)
        after = ([_stroke(n + i + 1, 650 + i * 20, 450, t_start=70000 + i * 500, phase="after")
                  for i in range(after_in_region)]
                 + [_stroke(n + after_in_region + i + 1, 120 + i * 20, 500,
                            t_start=80000 + i * 500, phase="after") for i in range(after_outside)])
        events = ([{"seq": 100, "t_ms": 65000, "type": "REVISION_START",
                    "payload": {"feedback_id": fb["feedback_id"], "latency_ms": 4000}}]
                  + [dict(e, seq=200 + i) for i, e in enumerate(_events(after))])
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": after, "events": events})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(before + after), "elapsed_ms": 120000, "phase": "after"})
        return sid, fb

    # -- the region has to be in stroke coordinates -------------------------
    def test_a_region_the_analysis_cannot_use_is_refused(self):
        sid = self._session()
        for bad in ({"shape": "rect", "coords": [0.2, 0.3, 0.4, 0.4]},   # fractions, not pixels
                    {"shape": "rect", "coords": [10, 10, 0, 50]},         # zero width
                    {"shape": "point", "coords": [10, 10]},               # no radius
                    {"shape": "poly", "coords": [0, 0, 10, 10]}):         # only two points
            r = self.c.post(f"/api/sessions/{sid}/feedback",
                            json={"source": "teacher", "text": "x", "target_region": bad})
            self.assertEqual(r.status_code, 422, bad)

    # -- feedback → subsequent revision ------------------------------------
    def test_revision_is_attributed_to_the_feedback_it_answers(self):
        sid, fb = self._drew_then_feedback_then_revised()
        rec = next(r for r in self.c.get(f"/api/sessions/{sid}/revision").json()["feedback"]
                   if r["feedback_id"] == fb["feedback_id"])

        self.assertEqual(rec["source"], "teacher")
        self.assertTrue(rec["has_region"])
        self.assertTrue(rec["revision"]["started"])
        self.assertTrue(rec["revision"]["linked"])          # names *this* feedback, not "a" feedback
        self.assertEqual(rec["revision"]["latency_ms"], 4000)

        # the number the experiments are after: work moved into the targeted region
        self.assertEqual(rec["before"]["strokes_in_region"], 0)
        self.assertEqual(rec["after"]["strokes_in_region"], 3)
        self.assertEqual(rec["before"]["share_in_region"], 0.0)
        self.assertGreater(rec["after"]["share_in_region"], 0.7)
        self.assertGreater(rec["region_shift"], 0.7)

    def test_ignoring_the_region_shows_up_as_no_shift(self):
        """A child who revises elsewhere must not look like one who complied."""
        sid, fb = self._drew_then_feedback_then_revised(after_in_region=0, after_outside=4)
        rec = next(r for r in self.c.get(f"/api/sessions/{sid}/revision").json()["feedback"]
                   if r["feedback_id"] == fb["feedback_id"])
        self.assertTrue(rec["revision"]["started"])          # they did revise…
        self.assertEqual(rec["after"]["strokes"], 4)
        self.assertEqual(rec["after"]["share_in_region"], 0.0)   # …just not there
        self.assertEqual(rec["region_shift"], 0.0)

    def test_undone_revision_strokes_do_not_count_as_acting_on_feedback(self):
        """A stroke drawn and immediately taken back is not a response."""
        sid = self._session()
        before = [_stroke(1, 100, 100, t_start=1000)]
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": before, "events": _events(before)})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(before), "elapsed_ms": 60000, "phase": "before"})
        fb = self.c.post(f"/api/sessions/{sid}/feedback", json={
            "source": "teacher", "text": "右下角", "t_ms": 61000,
            "target_region": REGION}).json()["feedback"]

        after = [_stroke(2, 650, 450, t_start=70000, phase="after")]
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": after, "events": [
            {"seq": 100, "t_ms": 65000, "type": "REVISION_START", "payload": {"feedback_id": fb["feedback_id"]}},
            {"seq": 101, "t_ms": 70000, "type": "STROKE", "payload": {"stroke_id": "s00002", "tool": "pencil", "n": 10}},
            {"seq": 102, "t_ms": 71000, "type": "UNDO",
             "payload": {"removed": ["s00002"], "restored": [], "visible_n": 1}}]})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(before), "elapsed_ms": 120000, "phase": "after"})

        # not [-1]: submitting the revision appends the AI's before/after comparison
        rec = next(r for r in self.c.get(f"/api/sessions/{sid}/revision").json()["feedback"]
                   if r["feedback_id"] == fb["feedback_id"])
        self.assertEqual(rec["after"]["strokes"], 0)
        # None, not 0.0: nothing survived to measure. "Revised somewhere else"
        # (0.0) and "revised nothing" are different outcomes and must not collapse.
        self.assertIsNone(rec["after"]["share_in_region"])
        self.assertIsNone(rec["region_shift"])

    def test_declining_to_revise_is_recorded_against_that_feedback(self):
        sid = self._session()
        strokes = [_stroke(1, 100, 100, t_start=1000)]
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": strokes, "events": _events(strokes)})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(strokes), "elapsed_ms": 60000, "phase": "before"})
        self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 65000})

        events = read_jsonl(SESSIONS / sid / "events.jsonl")
        skipped = next(e for e in events if e["type"] == "REVISION_SKIPPED")
        ai = session_feedback(SESSIONS / sid)[0]
        self.assertEqual(skipped["payload"]["feedback_id"], ai["feedback_id"])
        self.assertEqual(skipped["payload"]["latency_ms"], 5000)

        rec = self.c.get(f"/api/sessions/{sid}/revision").json()["feedback"][0]
        self.assertTrue(rec["revision"]["skipped"])
        self.assertFalse(rec["revision"]["started"])

    # -- a second rater -----------------------------------------------------
    def test_ratings_are_append_only_and_per_rater(self):
        sid, _ = self._drew_then_feedback_then_revised()
        for rater, overall in (("T-01", 4), ("T-02", 3)):
            r = self.c.post(f"/api/sessions/{sid}/rating", json={
                "source": "teacher", "rater_id": rater, "overall": overall,
                "dims": {"imagination": 4, "picture_organization": 3}, "note": "note", "t_ms": 130000})
            self.assertEqual(r.status_code, 200, r.text)

        rows = session_labels(SESSIONS / sid, "rating")
        self.assertEqual([r["rater_id"] for r in rows], ["T-01", "T-02"])   # nothing overwritten
        self.assertEqual(rows[0]["dims"]["imagination"], 4)
        self.assertEqual(len({r["rating_id"] for r in rows}), 2)
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["counts"]["ratings"], 2)

        self.assertEqual(self.c.post(f"/api/sessions/{sid}/rating",
                                     json={"overall": 9}).status_code, 422)
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/rating",
                                     json={"dims": {"not_a_dim": 3}}).status_code, 422)

    def test_export_carries_the_feedback_experiment_table(self):
        sid, _ = self._drew_then_feedback_then_revised()
        self.c.post(f"/api/sessions/{sid}/rating",
                    json={"source": "teacher", "rater_id": "T-09", "overall": 4})
        out = Path(tempfile.mkdtemp(prefix="artquest-fb-"))
        counts = export(out)
        self.assertGreaterEqual(counts["ratings"], 1)

        head = (out / "feedback.csv").read_text(encoding="utf-8").splitlines()[0]
        for col in ("has_region", "revision_started", "revision_linked", "latency_ms",
                    "share_in_region_before", "share_in_region_after", "region_shift"):
            self.assertIn(col, head)
        self.assertIn("dim_imagination", (out / "ratings.csv").read_text(encoding="utf-8").splitlines()[0])


if __name__ == "__main__":
    unittest.main()
