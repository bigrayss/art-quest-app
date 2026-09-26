"""The research data layer: identity, task metadata, frozen conditions,
append-only logs, idempotent ingest, QC, replay and dataset export.

Run:  python3 -m unittest -v
"""
import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from .env import TMP as _TMP, ADMIN  # sets the offline backends and the test data dir

from fastapi.testclient import TestClient  # noqa: E402

from artquest import events as ev  # noqa: E402
from artquest import study as study_mod  # noqa: E402
from artquest.main import app  # noqa: E402
from tools.export_dataset import export  # noqa: E402
from artquest.reconstruct import compare, read_jsonl, render  # noqa: E402
from artquest.storage import (SessionStore, decode_data_url,  # noqa: E402
                              session_feedback, session_part)
from tools.replay import replay_session  # noqa: E402

SESSIONS = Path(_TMP) / "sessions"


def _strokes(n=4, seq0=0):
    """Synthetic strokes: [x, y, dt_ms, pressure, tiltX, tiltY] per point."""
    out = []
    for i in range(n):
        y = 80 + i * 60
        pts = [[100.0 + j * 30, float(y + (j % 3)), j * 16, 0.4 + 0.05 * (j % 4), 3, -2] for j in range(12)]
        out.append({"seq": seq0 + i + 1, "stroke_id": f"s{i + 1:05d}", "phase": "before",
                    "t_start_ms": 1000 + i * 900, "t_end_ms": 1000 + i * 900 + 176,
                    "tool": ["pencil", "brush", "marker", "pencil"][i % 4],
                    "color": ["#222222", "#e63946", "#1d6fe0", "#2a9d8f"][i % 4],
                    "size": 4 + i, "opacity": 1.0, "erase": False, "pointer_type": "pen", "points": pts})
    return out


def _events(n=5, seq0=0):
    """Non-drawing events — safe to mix with any stroke log."""
    types = ["COLOR_CHANGE", "SIZE_CHANGE", "IDLE_START", "REFERENCE_OPEN", "BRUSH_CHANGE"]
    return [{"seq": seq0 + i + 1, "t_ms": 500 * (i + 1), "type": types[i % len(types)],
             "payload": {"color": "#e63946", "tool": "brush"}} for i in range(n)]


def _timeline(strokes, ops=()):
    """The timeline a client really produces: one STROKE per stroke, then `ops`.

    `ops` are extra `(type, payload)` pairs appended after the drawing, e.g.
    `("UNDO", {"removed": ["s00004"], "restored": [], "visible_n": 3})`.
    """
    out = [{"seq": i + 1, "t_ms": 500 * (i + 1), "type": "STROKE",
            "payload": {"stroke_id": s["stroke_id"], "tool": s["tool"],
                        "color": s["color"], "size": s["size"], "n": len(s["points"])}}
           for i, s in enumerate(strokes)]
    for j, (kind, payload) in enumerate(ops):
        out.append({"seq": len(strokes) + j + 1, "t_ms": 500 * (len(strokes) + j + 1),
                    "type": kind, "payload": payload})
    return out


def _png_of(strokes, size=(1024, 704)):
    buf = io.BytesIO()
    render(strokes, size).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class ResearchDataLayer(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app, headers=ADMIN)

    def _create(self, **over):
        body = {
            "quest_id": "imagine_animal",
            "intent": {"emotion": "开心", "text": "一只会飞的鱼"},
            "participant": {"anon_id": "anon-abc123", "participant_id": "P007"},
            "condition": {"ui": "quiet", "questionnaire": True},
            "device": {"platform": "Linux x86_64", "screen": [1920, 1080], "dpr": 2.0, "timezone": "Asia/Shanghai"},
            "canvas": {"width": 1024, "height": 704, "css_width": 900, "css_height": 619},
            "study": {"active": True, "study_id": "pilot1", "group": "A", "order_index": 2, "sequence_id": "a>b>c"},
        }
        body.update(over)
        r = self.c.post("/api/sessions", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["session_id"]

    # -- identity / task / condition ---------------------------------------
    def test_metadata_records_identity_task_condition_and_device(self):
        sid = self._create()
        m = self.c.get(f"/api/sessions/{sid}").json()
        self.assertEqual(m["schema_version"], 3)
        self.assertEqual(m["participant"],
                         {"anon_id": "anon-abc123", "participant_id": "P007", "account_id": "",
                          "label": "", "buddy_name": ""})
        self.assertEqual(m["task"]["task_id"], "imagine_animal")
        self.assertEqual(m["task"]["category"], "open_creation")   # = the family slug
        self.assertEqual(m["task"]["family"], "M0")                # the original open quests
        self.assertEqual(m["task"]["order_index"], 2)
        self.assertEqual(m["condition"]["ui"], "quiet")          # frozen at creation
        self.assertTrue(m["condition"]["questionnaire"])
        self.assertEqual(m["device"]["platform"], "Linux x86_64")
        self.assertEqual(m["canvas"]["width"], 1024)             # needed to replay faithfully
        self.assertEqual(m["study"]["study_id"], "pilot1")
        self.assertTrue(m["times"]["started_at"])
        self.assertTrue(any(e["type"] == "SESSION_START" for e in m["events"]))

    def test_open_task_gets_permissive_condition_values(self):
        """An open creative quest is a valid condition, not a missing field."""
        q = next(q for q in self.c.get("/api/quests").json() if q["id"] == "emotion_alone")
        self.assertIsNone(q["reference"])
        self.assertIsNone(q["time_limit_sec"])
        self.assertIsNone(q["allowed_tools"])
        self.assertEqual(q["task_id"], q["id"])

    # -- append-only, idempotent ingest ------------------------------------
    def test_log_ingest_is_idempotent(self):
        sid = self._create()
        batch = {"events": _events(5), "strokes": _strokes(4)}
        r1 = self.c.post(f"/api/sessions/{sid}/log", json=batch).json()["streams"]
        self.assertEqual(r1["events"]["written"], 5)
        self.assertEqual(r1["strokes"]["written"], 4)

        # a client that lost its connection re-sends the same batch
        r2 = self.c.post(f"/api/sessions/{sid}/log", json=batch).json()["streams"]
        self.assertEqual((r2["events"]["written"], r2["events"]["skipped"]), (0, 5))
        self.assertEqual(r2["strokes"]["written"], 0)

        # an overlapping batch only appends what is new
        r3 = self.c.post(f"/api/sessions/{sid}/log",
                         json={"events": _events(4, seq0=3), "strokes": []}).json()["streams"]
        self.assertEqual((r3["events"]["written"], r3["events"]["skipped"]), (2, 2))

        d = SESSIONS / sid
        self.assertEqual(len(read_jsonl(d / "strokes.jsonl")), 4)
        seqs = [e["seq"] for e in read_jsonl(d / "events.jsonl") if e.get("seq")]
        self.assertEqual(seqs, sorted(seqs))                     # append-only, in order
        self.assertEqual(len(set(seqs)), len(seqs))              # no duplicates
        m = self.c.get(f"/api/sessions/{sid}").json()
        self.assertEqual(m["counts"]["strokes"], 4)
        self.assertEqual(m["counts"]["points"], 48)

    def test_points_keep_pressure_and_tilt(self):
        sid = self._create()
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": _strokes(1)})
        pt = self.c.get(f"/api/sessions/{sid}/strokes").json()[0]["points"][0]
        self.assertEqual(len(pt), 6)                             # x, y, dt, pressure, tiltX, tiltY
        self.assertAlmostEqual(pt[3], 0.4)
        self.assertEqual(pt[4], 3)

    # -- feedback and what happens after it --------------------------------
    def test_feedback_is_structured_and_anchored_in_the_timeline(self):
        sid = self._create()
        strokes = _strokes(4)
        self.c.post(f"/api/sessions/{sid}/log", json={"events": _events(3), "strokes": strokes})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png_of(strokes), "elapsed_ms": 60000, "phase": "before"})

        fb = session_feedback(SESSIONS / sid)
        self.assertEqual(len(fb), 1)
        self.assertEqual(fb[0]["source"], "ai")
        self.assertEqual(fb[0]["phase"], "before")
        self.assertTrue(fb[0]["feedback_id"] and fb[0]["text"])

        # a teacher can add their own next to the AI's, pointing at a region.
        # canvas pixel space, not fractions: it has to be the same coordinates
        # the strokes are in, or "did they work there?" is not computable
        self.c.post(f"/api/sessions/{sid}/feedback",
                    json={"source": "teacher", "text": "试试把主体画大一点", "t_ms": 61000,
                          "target_region": {"shape": "rect", "coords": [200, 200, 400, 300],
                                            "label": "主体"}})
        fb = session_feedback(SESSIONS / sid)
        self.assertEqual([f["source"] for f in fb], ["ai", "teacher"])
        self.assertEqual(fb[1]["target_region"]["coords"], [200, 200, 400, 300])

        # a region the analysis could not use is refused at the door
        bad = self.c.post(f"/api/sessions/{sid}/feedback",
                          json={"source": "teacher", "text": "x", "t_ms": 62000,
                                "target_region": {"shape": "rect", "coords": [0.2, 0.3]}})
        self.assertEqual(bad.status_code, 422)

        # the event stream carries the anchor that splits before/after feedback
        events = read_jsonl(SESSIONS / sid / "events.jsonl")
        shown = [e for e in events if e["type"] == "FEEDBACK_SHOW"]
        self.assertEqual(len(shown), 2)
        self.assertEqual(shown[0]["payload"]["feedback_id"], fb[0]["feedback_id"])

        # …and revision strokes logged afterwards stay attributable to the "after" phase
        after = [dict(s, seq=s["seq"] + 10, phase="after") for s in _strokes(2)]
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": after})
        phases = [s["phase"] for s in self.c.get(f"/api/sessions/{sid}/strokes").json()]
        self.assertEqual(phases.count("after"), 2)

    # -- study mode --------------------------------------------------------
    def test_study_assignment_is_stable_and_counterbalanced(self):
        a = self.c.post("/api/study/assign", json={"participant_id": "P100", "anon_id": "anon-1"}).json()
        b = self.c.post("/api/study/assign", json={"participant_id": "P100", "anon_id": "anon-1"}).json()
        self.assertEqual(a["sequence"], b["sequence"])           # same code replays the same order
        ids = {q["id"] for q in self.c.get("/api/quests").json()}
        self.assertEqual(set(a["sequence"]), ids)                # a permutation, nothing dropped
        self.assertIn("ui", a["condition"])

        rows = [study_mod.task_sequence("x", ["a", "b", "c", "d"], "latin", i) for i in range(4)]
        for pos in range(4):                                     # every task in every position once
            self.assertEqual(len({r[pos] for r in rows}), 4)

    def test_conditions_can_be_frozen_per_group(self):
        study_mod.save_study({"active": True, "study_id": "s1", "order": "latin",
                              "condition": {"ui": "full", "questionnaire": True},
                              "groups": {"B": {"ui": "quiet", "undo_allowed": False}}})
        try:
            cond = study_mod.resolve_condition(group="B")
            self.assertEqual(cond["ui"], "quiet")
            self.assertFalse(cond["undo_allowed"])
            self.assertTrue(cond["questionnaire"])               # inherited from the study default
            sid = self._create(condition={}, study={"active": True, "study_id": "s1", "group": "B"})
            self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["condition"]["ui"], "quiet")
        finally:
            study_mod.save_study(dict(study_mod.DEFAULT_STUDY))

    # -- questionnaire + QC ------------------------------------------------
    def test_full_session_passes_qc_and_stores_self_report(self):
        sid = self._create()
        strokes = _strokes(6)
        self.c.post(f"/api/sessions/{sid}/log", json={"events": _timeline(strokes), "strokes": strokes})
        img = _png_of(strokes)
        self.c.post(f"/api/sessions/{sid}/submit", json={"image": img, "elapsed_ms": 60000, "phase": "before"})
        r = self.c.post(f"/api/sessions/{sid}/submit",
                        json={"image": img, "elapsed_ms": 120000, "phase": "after", "pending": 0}).json()
        self.assertTrue(r["qc"]["ok"], r["qc"]["failed"])
        self.assertEqual(r["qc"]["counts"]["strokes"], 6)

        q = self.c.post(f"/api/sessions/{sid}/questionnaire",
                        json={"difficulty": 4, "confidence": 3, "enjoyment": 5, "hardest_part": "比例"}).json()
        self.assertEqual(q["questionnaire"]["difficulty"], 4)
        self.assertTrue(session_part(SESSIONS / sid, "self_report"))
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["questionnaire"]["hardest_part"], "比例")
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/questionnaire", json={"difficulty": 9}).status_code, 422)

    def test_qc_flags_a_session_with_no_process_data(self):
        sid = self._create()
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png_of(_strokes(2)), "elapsed_ms": 1000, "phase": "before"})
        qc = self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 1200, "pending": 3}).json()["qc"]
        self.assertFalse(qc["ok"])
        for name in ("strokes_nonempty", "duration_plausible", "uploads_flushed"):
            self.assertIn(name, qc["failed"])

    # -- replay + export ---------------------------------------------------
    def test_session_replays_from_the_stroke_log_alone(self):
        sid = self._create()
        strokes = _strokes(8)
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": strokes, "events": _timeline(strokes)})
        img = _png_of(strokes)
        self.c.post(f"/api/sessions/{sid}/submit", json={"image": img, "elapsed_ms": 90000, "phase": "before"})
        self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 95000})

        rep = replay_session(sid, keyframes=True)
        self.assertEqual((rep["strokes_logged"], rep["strokes_visible"]), (8, 8))
        self.assertEqual(rep["streams"]["status"], "ok")
        self.assertEqual(rep["points"], 96)
        self.assertTrue(rep["replayable"], rep)
        self.assertEqual(rep["keyframes"], [10, 25, 50, 75, 100])
        for pct in (10, 50, 100):                                # key frames are generated, never stored
            self.assertTrue((SESSIONS / sid / "replay" / f"keyframe_{pct:03d}.png").exists())

    def _finished(self, strokes, ops, visible):
        """Run a whole session whose canvas ends up showing `visible`."""
        sid = self._create()
        # every stroke stays in the log, including the ones taken back off the canvas
        self.c.post(f"/api/sessions/{sid}/log",
                    json={"strokes": strokes, "events": _timeline(strokes, ops)})
        img = _png_of(visible)
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": img, "elapsed_ms": 60000, "phase": "before"})
        qc = self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 65000}).json()["qc"]
        return sid, qc

    def test_undone_strokes_are_not_painted_back(self):
        """The stroke log keeps them for ever; the artwork must not show them."""
        strokes = _strokes(5)
        ops = [("UNDO", {"removed": ["s00005"], "restored": [], "visible_n": 4}),
               ("UNDO", {"removed": ["s00004"], "restored": [], "visible_n": 3})]
        sid, qc = self._finished(strokes, ops, strokes[:3])

        self.assertTrue(qc["ok"], qc["failed"])
        self.assertEqual((qc["counts"]["strokes"], qc["counts"]["strokes_visible"]), (5, 3))
        self.assertEqual(qc["counts"]["strokes_removed"], 2)
        rep = replay_session(sid)
        self.assertEqual(rep["strokes_visible"], 3)
        self.assertTrue(rep["replayable"], rep)
        self.assertLess(rep["rel"], 0.02)                        # rebuilt == what was saved

        # This is the regression guard, not the QC threshold: replaying the raw
        # stroke list paints the two undone strokes back and no longer matches.
        # A fifth of the ink disagrees — real, but well under MAX_REPLAY_REL_DIFF,
        # which is why the trustworthy runtime check is `log_streams_agree`.
        naive = compare(render(strokes, (1024, 704)), render(strokes[:3], (1024, 704)))
        self.assertGreater(naive["rel"], 0.1)

    def test_clear_then_undo_restores_the_whole_canvas(self):
        strokes = _strokes(4)
        ids = [s["stroke_id"] for s in strokes]
        ops = [("CLEAR", {"removed": ids, "restored": [], "visible_n": 0}),
               ("UNDO", {"removed": [], "restored": ids, "visible_n": 4})]
        _, qc = self._finished(strokes, ops, strokes)
        self.assertTrue(qc["ok"], qc["failed"])
        self.assertEqual(qc["counts"]["strokes_visible"], 4)

    def test_a_log_without_undo_payloads_still_replays(self):
        """Sessions recorded before undo carried ids fall back to a linear stack."""
        strokes = _strokes(4)
        _, qc = self._finished(strokes, [("UNDO", None)], strokes[:3])
        self.assertTrue(qc["ok"], qc["failed"])
        self.assertEqual(qc["counts"]["strokes_visible"], 3)

    def test_qc_flags_logs_that_disagree_with_each_other(self):
        """A stroke that never reached the timeline is a lost batch, not a style."""
        strokes = _strokes(4)
        sid = self._create()
        self.c.post(f"/api/sessions/{sid}/log",
                    json={"strokes": strokes, "events": _timeline(strokes[:2])})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png_of(strokes), "elapsed_ms": 60000, "phase": "before"})
        qc = self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 65000}).json()["qc"]

        self.assertIn("log_streams_agree", qc["failed"])
        streams = next(c for c in qc["checks"] if c["name"] == "log_streams_agree")["detail"]
        self.assertEqual(streams["orphan_strokes"], ["s00003", "s00004"])
        self.assertFalse(replay_session(sid)["replayable"])

    def test_export_produces_flat_tables(self):
        sid = self._create()
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": _strokes(3), "events": _timeline(_strokes(3))})
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": _png_of(_strokes(3)), "elapsed_ms": 30000, "phase": "before"})
        out = Path(tempfile.mkdtemp(prefix="artquest-export-"))
        counts = export(out, with_points=True)
        self.assertGreaterEqual(counts["sessions"], 1)
        self.assertGreaterEqual(counts["strokes"], 3)
        self.assertGreaterEqual(counts["feedback"], 1)
        head = (out / "sessions.csv").read_text(encoding="utf-8").splitlines()[0]
        for col in ("participant_id", "task_id", "cond_ui", "n_strokes", "qc_ok", "duration_ms"):
            self.assertIn(col, head)
        points = (out / "points.csv").read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(points), 30)
        self.assertEqual(points[0].split(",")[3:6], ["x", "y", "t_ms"])

    # -- the older on-disk layout stays readable ---------------------------
    def test_a_session_recorded_in_the_old_layout_still_reads(self):
        """Fifteen files became four. Data already collected is not rewritten.

        This builds a session the way schema 2 wrote one — metadata.json plus
        five sidecars, strokes spelled `t_start_ms` / `pointer_type` / `erase` —
        and checks every reader folds it onto the current shape. If this breaks,
        every session collected before the convergence becomes unreadable, which
        is the one outcome the merge was not allowed to have.
        """
        d = SESSIONS / "0123456789ab"
        d.mkdir(parents=True)
        (d / "metadata.json").write_text(json.dumps({
            "schema_version": 2, "id": "0123456789ab", "session_id": "0123456789ab",
            "created_at": "2026-01-01T00:00:00+00:00", "quest_id": "emotion_alone",
            "participant": {"anon_id": "anon-old", "participant_id": "P001", "label": ""},
            "task": {"task_id": "emotion_alone"}, "status": "done",
            "counts": {"strokes": 1, "points": 2, "events": 1},
        }, ensure_ascii=False), encoding="utf-8")
        (d / "condition.json").write_text(json.dumps(
            {"task_id": "emotion_alone", "instruction": "画出孤独"}), encoding="utf-8")
        (d / "self_report.json").write_text(json.dumps({"difficulty": 3}), encoding="utf-8")
        (d / "personalization.json").write_text(json.dumps({"backend": "none"}), encoding="utf-8")
        (d / "quality.json").write_text(json.dumps({"ok": True, "failed": []}), encoding="utf-8")
        (d / "feedback.jsonl").write_text(json.dumps(
            {"feedback_id": "fb_old", "source": "ai", "text": "旧格式"}) + "\n", encoding="utf-8")
        (d / "ratings.jsonl").write_text(json.dumps(
            {"rating_id": "rt_old", "rater_id": "t1", "overall": 4}) + "\n", encoding="utf-8")
        (d / "annotations.jsonl").write_text(json.dumps(
            {"annotation_id": "an_old", "label": "planning", "t_start_ms": 0, "t_end_ms": 10}) + "\n",
            encoding="utf-8")
        (d / "strokes.jsonl").write_text(json.dumps(
            {"seq": 1, "stroke_id": "s00001", "t_start_ms": 100, "t_end_ms": 180,
             "pointer_type": "mouse", "erase": True, "tool": "eraser",
             "points": [[1, 2, 0, None, None, None], [3, 4, 80, None, None, None]]}) + "\n",
            encoding="utf-8")
        (d / "before.png").write_bytes(decode_data_url(_png_of([])))

        store = SessionStore(SESSIONS)
        self.assertEqual(store.condition_snapshot("0123456789ab")["instruction"], "画出孤独")
        self.assertEqual(store.self_report("0123456789ab")["difficulty"], 3)
        self.assertEqual(store.personalization("0123456789ab")["backend"], "none")
        self.assertEqual(session_part(d, "qc")["ok"], True)
        self.assertEqual([f["feedback_id"] for f in store.feedback_log("0123456789ab")], ["fb_old"])
        self.assertEqual([r["rating_id"] for r in store.labels("0123456789ab", "rating")], ["rt_old"])
        self.assertEqual([a["annotation_id"] for a in
                          store.labels("0123456789ab", "process_annotation")], ["an_old"])
        # stroke fields folded, and the derivable one recomputed rather than read
        s = store.strokes("0123456789ab")[0]
        self.assertEqual((s["t0_ms"], s["pointer"], s["op"]), (100, "mouse", "erase"))
        self.assertNotIn("t_end_ms", s)
        self.assertEqual(ev.stroke_end_ms(s), 180)
        # a phase is not a file name: the old before.png still answers for it
        self.assertEqual(self.c.get("/files/0123456789ab/before.png").status_code, 200)
        # and it is still one of the participant's sessions
        hist = self.c.get("/api/participants/P001/history").json()["tasks"]
        self.assertIn("0123456789ab", [t.get("session_id") or t.get("id") for t in hist])


if __name__ == "__main__":
    unittest.main()
