# -*- coding: utf-8 -*-
"""One timeline, one clock, and nothing invented along the way.

The process layer's job is to be trustworthy rather than complete: a value that
was never measured must not arrive as a plausible number, a renamed event must
not orphan the sessions already collected, and a session whose last batch never
uploaded must not look finished.
"""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path

from .env import TMP as _TMP

from fastapi.testclient import TestClient  # noqa: E402

from artquest import events as ev  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.reconstruct import boundaries, read_jsonl, render  # noqa: E402
from tools.export_dataset import export  # noqa: E402
from tools.replay import replay_session  # noqa: E402
from tools.withdraw import withdraw  # noqa: E402

SESSIONS = Path(_TMP) / "sessions"


def _stroke(i, *, t_start, pressure=None, phase="before"):
    """`pressure=None` is what a mouse must produce: no reading, not 0.5."""
    pts = [[100.0 + j * 20, 200.0 + i * 40, j * 16, pressure,
            None if pressure is None else 3, None if pressure is None else -2]
           for j in range(10)]
    return {"seq": i, "stroke_id": f"s{i:05d}", "phase": phase,
            "t_start_ms": t_start, "t_end_ms": t_start + 160, "tool": "pencil",
            "color": "#222222", "size": 4, "opacity": 1.0, "erase": False,
            "pointer_type": "mouse" if pressure is None else "pen",
            "pressure_supported": pressure is not None,
            "tilt_supported": pressure is not None, "zoom": 1.0, "points": pts}


def _events(strokes):
    out = []
    for i, s in enumerate(strokes):
        out.append({"seq": 2 * i + 1, "t_ms": s["t_start_ms"], "type": ev.STROKE_START,
                    "payload": {"stroke_id": s["stroke_id"], "tool": s["tool"]}})
        out.append({"seq": 2 * i + 2, "t_ms": s["t_end_ms"], "type": ev.STROKE_END,
                    "payload": {"stroke_id": s["stroke_id"], "tool": s["tool"],
                                "n": len(s["points"])}})
    return out


def _png(strokes):
    buf = io.BytesIO()
    render(strokes, (1024, 704)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class EventVocabulary(unittest.TestCase):
    def test_renamed_events_do_not_orphan_old_sessions(self):
        for old, new in (("STROKE", ev.STROKE_END), ("IDLE_START", ev.PAUSE_START),
                         ("IDLE_END", ev.PAUSE_END), ("FEEDBACK_SHOWN", ev.FEEDBACK_SHOW)):
            self.assertEqual(ev.canonical(old), new)
            self.assertTrue(ev.is_known(old), f"{old} must stay readable")

    def test_a_module_inventing_its_own_name_is_detectable(self):
        self.assertEqual(ev.unknown_types([ev.ZOOM, "SOMETHING_ELSE"]), {"SOMETHING_ELSE"})

    def test_the_client_only_emits_names_the_vocabulary_knows(self):
        """The JS mirror of the vocabulary must not drift from the Python one."""
        js = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
        block = js.split("const EV = {", 1)[1].split("};", 1)[0]
        names = {p.split(":")[1].strip().strip('",') for p in block.split(",") if ":" in p}
        self.assertTrue(names)
        self.assertEqual(sorted(n for n in names if not ev.is_known(n)), [])


class HonestSignals(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def _session(self, task_id="emotion_alone"):
        return self.c.post("/api/sessions", json={
            "task_id": task_id, "intent": {"emotion": "平静", "text": "过程层"},
            "participant": {"anon_id": "anon-proc", "participant_id": "P-PROC"},
            "canvas": {"width": 1024, "height": 704}}).json()["session_id"]

    def test_an_unmeasured_channel_stays_null_end_to_end(self):
        sid = self._session()
        strokes = [_stroke(1, t_start=1000), _stroke(2, t_start=2000, pressure=0.7)]
        r = self.c.post(f"/api/sessions/{sid}/log",
                        json={"strokes": strokes, "events": _events(strokes)})
        self.assertEqual(r.status_code, 200, r.text)

        stored = self.c.get(f"/api/sessions/{sid}/strokes").json()
        self.assertFalse(stored[0]["pressure_supported"])
        self.assertIsNone(stored[0]["points"][0][3], "pressure was fabricated on the way in")
        self.assertIsNone(stored[0]["points"][0][4])
        self.assertEqual(stored[1]["points"][0][3], 0.7)

        # …and it still replays: the renderer needs a width, the log does not
        img = render([stored[0]], (1024, 704))
        self.assertGreater(img.size[0], 0)

        out = Path(tempfile.mkdtemp(prefix="artquest-proc-"))
        export(out, with_points=True)
        rows = (out / "strokes.csv").read_text(encoding="utf-8").splitlines()
        head = rows[0].split(",")
        self.assertIn("pressure_supported", head)
        mine = [r for r in rows[1:] if sid in r]
        col = head.index("mean_pressure")
        # a mean over values nobody measured would be worse than no mean
        self.assertEqual(mine[0].split(",")[col], "")
        self.assertTrue(mine[1].split(",")[col])

    def test_semantic_keyframes_sit_where_the_intervention_was(self):
        sid = self._session()
        before = [_stroke(i + 1, t_start=1000 + i * 1000) for i in range(3)]
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": before, "events": _events(before)})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(before), "elapsed_ms": 60000, "phase": "before"})
        after = [_stroke(4, t_start=70000, phase="after"), _stroke(5, t_start=71000, phase="after")]
        self.c.post(f"/api/sessions/{sid}/log", json={
            "strokes": after,
            "events": [{"seq": 100, "t_ms": 65000, "type": ev.REVISION_START, "payload": {}}]
                      + [dict(e, seq=200 + i) for i, e in enumerate(_events(after))]})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(before + after), "elapsed_ms": 120000, "phase": "after"})

        rep = replay_session(sid, keyframes=True)
        names = {b["name"]: b for b in rep["boundaries"]}
        self.assertIn("before_feedback", names)
        self.assertIn("before_revision", names)
        # what the artwork looked like when the feedback landed — 25/50/75 % cannot say
        self.assertEqual(names["before_feedback"]["n_strokes"], 3)
        self.assertEqual(names["after_revision"]["n_strokes"], 5)
        for name in ("before_feedback", "before_revision", "after_revision"):
            self.assertTrue((SESSIONS / sid / "replay" / f"keyframe_{name}.png").exists(), name)

    def test_expert_process_labels_are_spans_not_strokes(self):
        sid = self._session()
        ok = self.c.post(f"/api/sessions/{sid}/annotation", json={
            "rater_id": "E-01", "label": "turning_point", "t_start_ms": 12000,
            "t_end_ms": 18000, "confidence": 4, "note": "改了主体位置"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.c.post(f"/api/sessions/{sid}/annotation", json={
            "rater_id": "E-02", "label": "planning", "t_start_ms": 0, "t_end_ms": 9000})

        for bad in ({"label": "vibes", "t_start_ms": 0, "t_end_ms": 10},
                    {"label": "planning", "t_start_ms": 900, "t_end_ms": 100}):
            self.assertEqual(self.c.post(f"/api/sessions/{sid}/annotation", json=bad).status_code, 422)

        got = self.c.get(f"/api/sessions/{sid}/annotation").json()
        self.assertEqual([a["rater_id"] for a in got["annotations"]], ["E-01", "E-02"])
        self.assertEqual(len({a["annotation_id"] for a in got["annotations"]}), 2)
        self.assertIn("turning_point", got["labels"])

        out = Path(tempfile.mkdtemp(prefix="artquest-ann-"))
        counts = export(out)
        self.assertGreaterEqual(counts["annotations"], 2)
        head = (out / "annotations.csv").read_text(encoding="utf-8").splitlines()[0]
        for col in ("label", "t_start_ms", "duration_ms", "rater_id"):
            self.assertIn(col, head)

    def test_the_closed_self_report_answer_is_validated(self):
        sid = self._session()
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png([]), "elapsed_ms": 60000, "phase": "before"})
        ok = self.c.post(f"/api/sessions/{sid}/questionnaire", json={
            "difficulty": 3, "hardest_part_choice": "proportion", "hardest_part": "房子"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/questionnaire",
                                     json={"hardest_part_choice": "banana"}).status_code, 422)
        # written under the name §14 asks for, and still reachable as before
        self.assertTrue((SESSIONS / sid / "self_report.json").exists())
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["questionnaire"]["hardest_part_choice"],
                         "proportion")


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def _run(self, pending):
        sid = self.c.post("/api/sessions", json={
            "task_id": "emotion_alone", "intent": {"emotion": "平静", "text": ""},
            "participant": {"anon_id": "anon-life", "participant_id": "P-LIFE"},
            "canvas": {"width": 1024, "height": 704}}).json()["session_id"]
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["lifecycle"], "recording")
        strokes = [_stroke(1, t_start=1000)]
        self.c.post(f"/api/sessions/{sid}/log",
                    json={"strokes": strokes, "events": _events(strokes), "pending": pending})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png(strokes), "elapsed_ms": 60000, "phase": "before"})
        self.c.post(f"/api/sessions/{sid}/finalize",
                    json={"elapsed_ms": 65000, "pending": pending})
        return sid

    def test_a_session_whose_last_batch_never_landed_is_not_verified(self):
        sid = self._run(pending=3)
        meta = self.c.get(f"/api/sessions/{sid}").json()
        # finished for the child, not finished for the data
        self.assertEqual(meta["status"], "done")
        self.assertEqual(meta["lifecycle"], "pending_upload")
        self.assertIn("uploads_flushed", meta["qc"]["failed"])

        # the queue drains later; the session catches up
        self.c.post(f"/api/sessions/{sid}/log", json={"events": [], "strokes": [], "pending": 0})
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["lifecycle"], "uploaded")
        qc = self.c.post(f"/api/sessions/{sid}/qc").json()
        self.assertNotIn("uploads_flushed", qc["failed"])
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["lifecycle"], "server_verified")

    def test_a_clean_run_reaches_verified_and_never_goes_back(self):
        sid = self._run(pending=0)
        meta = self.c.get(f"/api/sessions/{sid}").json()
        self.assertEqual(meta["lifecycle"], "server_verified")
        self.assertTrue((SESSIONS / sid / "quality.json").exists())
        self.assertTrue(meta["qc"]["checks"])
        checksum = next(c for c in meta["qc"]["checks"] if c["name"] == "log_checksum")["detail"]
        self.assertIn("strokes", checksum)

        # a late duplicate batch must not demote a verified session
        self.c.post(f"/api/sessions/{sid}/log", json={"events": [], "strokes": [], "pending": 5})
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["lifecycle"], "server_verified")

    def test_the_stimulus_travels_with_the_session(self):
        sid = self.c.post("/api/sessions", json={
            "task_id": "M1_A", "intent": {"emotion": "好奇", "text": ""},
            "participant": {"participant_id": "P-REF"},
            "canvas": {"width": 1024, "height": 704}}).json()["session_id"]
        meta = self.c.get(f"/api/sessions/{sid}").json()
        # the file in static/refs will be replaced; the session must stay self-contained
        self.assertTrue(meta["task"]["reference_file"])
        self.assertTrue((SESSIONS / sid / meta["task"]["reference_file"]).exists())
        qc = self.c.post(f"/api/sessions/{sid}/qc").json()
        self.assertNotIn("reference_available", qc["failed"])


class Withdrawal(unittest.TestCase):
    def test_withdrawing_really_removes_the_data_but_keeps_the_slot(self):
        c = TestClient(app)
        pid = "P-WITHDRAW"
        sids = []
        for _ in range(2):
            sid = c.post("/api/sessions", json={
                "task_id": "emotion_alone", "intent": {"emotion": "平静", "text": "x"},
                "participant": {"anon_id": f"anon-{pid}", "participant_id": pid},
                "canvas": {"width": 1024, "height": 704}}).json()["session_id"]
            sids.append(sid)
        import artquest.study as study_mod
        study_mod.register_participant(pid, f"anon-{pid}")
        index_before = study_mod.roster_entry(pid)["index"]

        dry = withdraw(pid, confirm=False)
        self.assertTrue(dry["dry_run"])
        self.assertEqual(dry["sessions_removed"], 2)
        self.assertTrue(all((SESSIONS / s).exists() for s in sids), "a dry run must not delete")

        receipt = withdraw(pid, confirm=True)
        self.assertFalse(receipt["dry_run"])
        self.assertEqual(sorted(receipt["session_ids"]), sorted(sids))
        self.assertFalse(any((SESSIONS / s).exists() for s in sids))
        # the receipt is auditable and holds nothing that was withdrawn
        self.assertNotIn("intent", json.dumps(receipt))

        entry = study_mod.roster_entry(pid)
        self.assertTrue(entry["withdrawn"])
        # the index stays taken: otherwise the next participant inherits their
        # task order and quietly becomes them in the analysis
        self.assertEqual(entry["index"], index_before)


if __name__ == "__main__":
    unittest.main()
