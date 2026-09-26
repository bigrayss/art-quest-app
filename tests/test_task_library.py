# -*- coding: utf-8 -*-
"""The task as a measurement object: library, rubric contract, condition, protocol.

A task_id is a foreign key in every table that follows. These tests hold the
properties that make it one: ids are stable and machine-safe, a task declares
what it can and cannot measure, what the child saw is frozen, and the order they
saw it in is checkable rather than assumed.
"""
import base64
import io
import json
import re
import unittest
from pathlib import Path

from .env import TMP as _TMP, ADMIN

from fastapi.testclient import TestClient  # noqa: E402

from artquest import quests as quests_mod  # noqa: E402
from artquest import study as study_mod  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.missions import FAMILIES, build_library  # noqa: E402
from artquest.reconstruct import ink_ratio, render  # noqa: E402
from artquest.rubric import RubricError, apply_contract, normalize  # noqa: E402
from artquest.scoring.base import DIM_KEYS  # noqa: E402

SESSIONS = Path(_TMP) / "sessions"


class TaskLibrary(unittest.TestCase):
    def test_every_form_has_a_stable_machine_safe_id(self):
        lib = build_library()
        ids = [t["task_id"] for t in lib]
        self.assertEqual(len(ids), len(set(ids)), "duplicate task_id")
        for tid in ids:
            # ids end up in filenames, CSV headers and foreign keys
            self.assertRegex(tid, r"^[A-Za-z0-9_]+$", tid)
        self.assertEqual(ids, [t["task_id"] for t in build_library()], "ids must not drift")
        self.assertGreaterEqual(len({t["family"] for t in lib}), 10)

    def test_the_original_quests_still_resolve(self):
        """Sessions already collected against these ids stay interpretable."""
        for legacy in ("emotion_alone", "imagine_animal", "transform_chair",
                       "color_rain_city", "story_character_home"):
            task = quests_mod.get_quest(legacy)
            self.assertIsNotNone(task, legacy)
            self.assertEqual(task["family"], "M0")

    def test_generated_families_vary_the_condition_they_are_built_on(self):
        by_family = {}
        for t in build_library():
            by_family.setdefault(t["family"], []).append(t)
        m4 = by_family["M4"]
        self.assertEqual({t["prompt_style"] for t in m4}, {"minimal", "story", "challenge"})
        # the card combination is recorded, not just baked into the sentence
        self.assertTrue(all({"base_object", "environment", "goal"} <= set(t["condition"]) for t in m4))
        self.assertGreaterEqual(len({t["condition"]["base_object"] for t in m4}), 5)

    def test_every_drawing_is_scored_on_all_nine(self):
        """A task says what it *additionally* elicits, not what gets measured.

        M1 is the case that used to be wrong: it was marked "pencil only, so no
        colour", but `allowed_tools` only disables the brush buttons — the
        palette is there and the pencil paints in the chosen colour. So a M1
        drawing can be colourful, and its colour is measured like everything else.
        """
        for tid in ("M1_A", "M2_A", "M6_A_calm"):
            q = quests_mod.get_quest(tid)
            self.assertEqual(q["rubric"]["not_applicable_dimensions"], [], tid)
            self.assertEqual(sorted(q["applicable_dims"]), sorted(DIM_KEYS), tid)
        m1 = quests_mod.get_quest("M1_A")
        # what it focuses on is still declared, and still drives the UI + growth
        self.assertIn("realism", m1["rubric"]["primary_dimensions"])
        self.assertIn("color_richness", m1["rubric"]["exploratory_dimensions"])
        # silence means exploratory — scored, with no claim attached — never N/A
        self.assertEqual(sorted(sum(m1["rubric_summary"].values(), [])), sorted(DIM_KEYS))

    def test_a_task_cannot_opt_out_of_a_dimension(self):
        """"Not what this task is about" is not a reason to stop measuring it."""
        with self.assertRaises(RubricError) as caught:
            normalize({"primary_dimensions": ["realism"],
                       "not_applicable_dimensions": ["color_richness"],
                       "na_reason": {"color_richness": "这个任务不关心颜色"}},
                      task_id="T", allowed_tools=["pencil", "eraser"])
        self.assertIn("every dimension is scored", str(caught.exception))
        # …but a condition that really removes the channel derives it, with a reason
        r = normalize({"primary_dimensions": ["realism"]}, task_id="T",
                      allowed_tools=["eraser", "undo"])
        self.assertEqual(r["not_applicable_dimensions"], ["color_richness", "color_contrast"])
        self.assertTrue(r["na_reason"]["color_richness"])

    def test_an_uninterpretable_rubric_is_refused(self):
        for bad, why in (({"primary_dimensions": ["not_a_dim"]}, "unknown dimension"),
                         ({"primary_dimensions": ["realism"], "secondary_dimensions": ["realism"]}, "two roles"),
                         ({"not_applicable_dimensions": ["realism"]}, "cannot be declared")):
            with self.assertRaises(RubricError, msg=why):
                normalize(bad, task_id="T")

    def test_not_applicable_is_never_a_low_score(self):
        # the only way to get an N/A: a condition with nothing to draw colour with
        rubric = normalize({}, allowed_tools=["eraser", "undo"])
        # a backend that scored it anyway does not get to keep the number
        out = apply_contract({"dims": {"color_richness": {"score": 1, "note": "很少用色"},
                                       "realism": {"score": 4, "note": "x"}}}, rubric)
        self.assertIsNone(out["dims"]["color_richness"]["score"])
        self.assertTrue(out["dims"]["color_richness"]["na"])
        self.assertEqual(out["dims"]["realism"]["score"], 4)
        self.assertNotIn("color_richness", out["applicable"])


class ConditionSnapshot(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app, headers=ADMIN)

    def _create(self, task_id="M4_UMB_UW_TRA_story", **over):
        body = {"task_id": task_id, "intent": {"emotion": "好奇", "text": "t"},
                "participant": {"anon_id": "anon-lib", "participant_id": "P-LIB"},
                "canvas": {"width": 1024, "height": 704}}
        body.update(over)
        r = self.c.post("/api/sessions", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["session_id"]

    def test_what_the_child_saw_is_frozen_beside_the_session(self):
        sid = self._create()
        snap = json.loads((SESSIONS / sid / "session.json").read_text(encoding="utf-8"))["task"]
        # a task_id alone cannot recover this once tasks.json moves on
        self.assertEqual(snap["task_id"], "M4_UMB_UW_TRA_story")
        self.assertEqual((snap["family"], snap["form_id"], snap["prompt_style"]),
                         ("M4", "UMB_UW_TRA_story", "story"))
        self.assertIn("雨伞", snap["instruction"])
        self.assertEqual(snap["task_condition"]["base_object"], "umbrella")
        self.assertTrue(snap["rubric"]["primary_dimensions"])
        self.assertTrue(snap["process_targets"])
        self.assertTrue(snap["app_version"])
        self.assertEqual(snap["stimulus"]["kind"], "reference")

        m = self.c.get(f"/api/sessions/{sid}").json()
        self.assertEqual(m["task"]["prompt_style"], "story")
        self.assertTrue(any(e["type"] == "TASK_SHOW" for e in m["events"]))

    def test_a_session_run_on_a_placeholder_stimulus_says_so(self):
        sid = self._create()
        m = self.c.get(f"/api/sessions/{sid}").json()
        # pilot data is not invalid data — it is marked, not blocked
        self.assertTrue(m["task"]["stimulus_placeholder"])
        qc = self.c.post(f"/api/sessions/{sid}/qc").json()
        self.assertIn("stimulus_ready", qc["failed"])
        self.assertNotIn("condition_frozen", qc["failed"])

    def test_a_rater_scores_every_dimension_of_the_drawing(self):
        """A teacher rates all nine; the task only says which ones it focuses on."""
        sid = self._create("M1_A")
        ok = self.c.post(f"/api/sessions/{sid}/rating",
                         json={"source": "teacher", "rater_id": "T1",
                               "dims": {"color_richness": 2, "realism": 4}})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(ok.json()["rating"]["rubric_version"])
        self.assertEqual(ok.json()["rating"]["dims"]["color_richness"], 2)

    def test_a_fragment_task_does_not_start_on_a_blank_canvas(self):
        """Replay is `initial canvas + strokes + events` — the canvas counts."""
        sid = self._create("M3_A")
        snap = json.loads((SESSIONS / sid / "session.json").read_text(encoding="utf-8"))["task"]
        stim = snap["stimulus"]
        self.assertEqual(stim["kind"], "fragments")
        self.assertGreaterEqual(len(stim["items"]), 5)

        blank = render([], (1024, 704))
        seeded = render([], (1024, 704), stimulus=stim)
        self.assertEqual(ink_ratio(blank), 0.0)
        self.assertGreater(ink_ratio(seeded), 0.002)

        # …and the reconstruction picks it up from the frozen condition
        buf = io.BytesIO()
        seeded.save(buf, "PNG")
        img = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        stroke = {"seq": 1, "stroke_id": "s00001", "phase": "before", "t_start_ms": 0,
                  "t_end_ms": 100, "tool": "pencil", "color": "#222222", "size": 4,
                  "opacity": 1.0, "erase": False, "pointer_type": "mouse", "zoom": 1.0,
                  "points": [[100.0 + j * 20, 620.0, j * 10, 0.5, 0, 0] for j in range(10)]}
        self.c.post(f"/api/sessions/{sid}/log", json={
            "strokes": [stroke],
            "events": [{"seq": 1, "t_ms": 0, "type": "STROKE",
                        "payload": {"stroke_id": "s00001", "tool": "pencil", "n": 10}}]})
        buf2 = io.BytesIO()
        render([stroke], (1024, 704), stimulus=stim).save(buf2, "PNG")
        final = "data:image/png;base64," + base64.b64encode(buf2.getvalue()).decode()
        self.c.post(f"/api/sessions/{sid}/submit",
                    json={"image": final, "elapsed_ms": 60000, "phase": "before"})
        qc = self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 65000}).json()["qc"]
        detail = next(c for c in qc["checks"] if c["name"] == "replay_matches_final")["detail"]
        self.assertLess(detail["rel"], 0.05, "the replay must include the starting fragments")
        del img


class Protocol(unittest.TestCase):
    PROTO = {"protocol_id": "pilot1", "required_families": ["M1", "M3", "M4", "M6", "M9"],
             "anchor_task": "M1_A", "heldout_task": "M9_A", "prompt_style_rule": "balanced"}

    def test_each_participant_gets_one_form_per_family(self):
        for i in range(8):
            order = study_mod.plan(f"P{i:03d}", i, self.PROTO)["planned_order"]
            fams = [quests_mod.QUESTS_BY_ID[t]["family"] for t in order]
            self.assertEqual(len(fams), len(set(fams)), fams)
            self.assertEqual(len(fams), 5, fams)
            # the anchor and the held-out task replace their family's slot
            self.assertEqual(order[0], "M1_A")
            self.assertEqual(order[-1], "M9_A")

    def test_the_free_positions_are_counterbalanced(self):
        seen = {}
        for i in range(12):
            order = study_mod.plan(f"P{i:03d}", i, self.PROTO)["planned_order"]
            for pos, tid in enumerate(order[1:-1]):
                fam = quests_mod.QUESTS_BY_ID[tid]["family"]
                seen.setdefault(fam, [0, 0, 0])[pos] += 1
        for fam, counts in seen.items():
            self.assertEqual(counts, [4, 4, 4], f"{fam} is not counterbalanced: {counts}")

    def test_a_plan_replays_for_the_same_participant(self):
        a = study_mod.plan("P042", 42, self.PROTO)["planned_order"]
        b = study_mod.plan("P042", 42, self.PROTO)["planned_order"]
        self.assertEqual(a, b)

    def test_actual_order_is_checked_against_the_plan(self):
        c = TestClient(app, headers=ADMIN)
        study_mod.save_study({"active": True, "study_id": "proto", "order": "latin",
                              "protocol": self.PROTO})
        try:
            pid = "P-PROTO"
            assigned = c.post("/api/study/assign", json={"participant_id": pid}).json()
            planned = assigned["planned_order"]
            self.assertEqual(assigned["protocol_id"], "pilot1")
            self.assertTrue(planned)

            before = c.get(f"/api/participants/{pid}/protocol").json()
            self.assertEqual(before["completed"], 0)
            self.assertEqual(before["missing"], planned)

            # run the first planned task, but then run one that was never planned
            for task_id in (planned[0], "M5_CAT_AIRPLANE_B"):
                sid = c.post("/api/sessions", json={
                    "task_id": task_id, "intent": {"emotion": "好奇", "text": ""},
                    "participant": {"anon_id": f"anon-{pid}", "participant_id": pid},
                    "canvas": {"width": 1024, "height": 704}}).json()["session_id"]
                c.post(f"/api/sessions/{sid}/submit", json={
                    "image": _blank(), "elapsed_ms": 60000, "phase": "before"})
                c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 65000})

            after = c.get(f"/api/participants/{pid}/protocol").json()
            self.assertEqual(after["completed"], 2)
            self.assertEqual(after["actual_order"][0], planned[0])
            # task order is a confound: a run that drifted has to be visible
            self.assertFalse(after["followed_plan"])
            self.assertEqual(after["unplanned"], ["M5_CAT_AIRPLANE_B"])
        finally:
            study_mod.save_study(dict(study_mod.DEFAULT_STUDY))


def _blank():
    buf = io.BytesIO()
    render([], (1024, 704)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class ResearcherOverrides(unittest.TestCase):
    def test_a_researcher_adds_a_task_without_touching_code(self):
        path = Path(_TMP) / "tasks.json"
        path.write_text(json.dumps([{
            "task_id": "M4_CUSTOM_01", "family": "M4", "form_id": "CUSTOM_01",
            "title": "自定义", "instruction": "把台灯改造成沙漠里的家。",
            "prompt_style": "minimal", "time_limit_sec": 300,
            "condition": {"base_object": "lamp", "environment": "desert", "goal": "home"},
            "rubric": {"primary_dimensions": ["transformation"]},
        }]), encoding="utf-8")
        try:
            tasks = {t["task_id"]: t for t in quests_mod.reload_quests()}
            self.assertIn("M4_CUSTOM_01", tasks)
            self.assertEqual(tasks["M4_CUSTOM_01"]["time_limit_sec"], 300)
            # a researcher-added task is scored on all nine too
            self.assertEqual(len(tasks["M4_CUSTOM_01"]["applicable_dims"]), len(DIM_KEYS))
            self.assertIn("M4_UMB_UW_TRA_story", tasks)     # built-ins survive
        finally:
            path.unlink()
            quests_mod.reload_quests()

    def test_an_invalid_task_is_dropped_not_silently_accepted(self):
        path = Path(_TMP) / "tasks.json"
        path.write_text(json.dumps([
            {"task_id": "BAD_01", "title": "坏的", "instruction": "x",
             "rubric": {"primary_dimensions": ["not_a_dimension"]}},
            {"task_id": "GOOD_01", "title": "好的", "instruction": "y",
             "rubric": {"primary_dimensions": ["imagination"]}},
        ]), encoding="utf-8")
        try:
            tasks = {t["task_id"] for t in quests_mod.reload_quests()}
            self.assertNotIn("BAD_01", tasks)
            self.assertIn("GOOD_01", tasks)
        finally:
            path.unlink()
            quests_mod.reload_quests()


if __name__ == "__main__":
    unittest.main()
