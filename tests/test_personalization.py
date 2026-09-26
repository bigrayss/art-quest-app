"""User → multiple tasks → representation → a new task → prediction.

The pipeline is only real if each arrow is checked: that a participant's
finished tasks turn into a representation, that the representation is rebuilt
from the logs rather than cached, that the arm actually used is recorded even
when it is not the arm requested, and that the prediction written down before
the child drew is scored against the self-report afterwards.
"""
import base64
import io
import json
import unittest
from pathlib import Path

from .env import TMP as _TMP, ADMIN  # sets the offline backends and the test data dir

from fastapi.testclient import TestClient  # noqa: E402

from artquest import history as history_mod  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.personalize import get_personalizer  # noqa: E402
from artquest.reconstruct import render  # noqa: E402
from tools.export_dataset import export  # noqa: E402

SESSIONS = Path(_TMP) / "sessions"
PID = "P-HIST-01"


def _strokes(n, seq0=0, x0=100):
    out = []
    for i in range(n):
        y = 80 + i * 40
        pts = [[x0 + j * 30.0, float(y + (j % 3)), j * 16, 0.5, 0, 0] for j in range(12)]
        out.append({"seq": seq0 + i + 1, "stroke_id": f"s{i + 1:05d}", "phase": "before",
                    "t_start_ms": 1000 + i * 900, "t_end_ms": 1176 + i * 900,
                    "tool": ["pencil", "brush", "marker"][i % 3], "color": ["#222222", "#e63946"][i % 2],
                    "size": 4, "opacity": 1.0, "erase": False, "pointer_type": "mouse",
                    "zoom": 1.0, "points": pts})
    return out


def _timeline(strokes, extra=()):
    out = [{"seq": i + 1, "t_ms": 500 * (i + 1), "type": "STROKE",
            "payload": {"stroke_id": s["stroke_id"], "tool": s["tool"], "color": s["color"],
                        "size": s["size"], "n": len(s["points"])}}
           for i, s in enumerate(strokes)]
    for j, (kind, payload) in enumerate(extra):
        out.append({"seq": len(strokes) + j + 1, "t_ms": 500 * (len(strokes) + j + 1),
                    "type": kind, "payload": payload})
    return out


def _png(strokes):
    buf = io.BytesIO()
    render(strokes, (1024, 704)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class PersonalizationPipeline(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app, headers=ADMIN)

    def _run_task(self, task_id, *, pid=PID, n_strokes=4, extra=(), self_report=None,
                  condition=None, elapsed=90000):
        """One complete task for one participant, logs and all."""
        body = {"quest_id": task_id, "intent": {"emotion": "好奇", "text": f"做 {task_id}"},
                "participant": {"anon_id": f"anon-{pid}", "participant_id": pid},
                "condition": condition or {}, "canvas": {"width": 1024, "height": 704}}
        r = self.c.post("/api/sessions", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        created = r.json()
        sid = created["session_id"]

        strokes = _strokes(n_strokes)
        self.c.post(f"/api/sessions/{sid}/log", json={"strokes": strokes, "events": _timeline(strokes, extra)})
        img = _png(strokes)
        self.c.post(f"/api/sessions/{sid}/submit", json={"image": img, "elapsed_ms": elapsed, "phase": "before"})
        self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": elapsed + 5000})
        q = None
        if self_report:
            q = self.c.post(f"/api/sessions/{sid}/questionnaire", json=self_report).json()
        return sid, created, q

    # -- history → representation -----------------------------------------
    def test_finished_tasks_become_a_representation(self):
        pid = "P-REP-01"
        self._run_task("emotion_alone", pid=pid, n_strokes=4,
                       extra=[("UNDO", {"removed": ["s00004"], "restored": [], "visible_n": 3}),
                              ("ZOOM", {"from": 1, "to": 4, "source": "wheel", "steps": [[0, 4]]}),
                              ("IDLE_END", {"duration_ms": 70000})],
                       self_report={"difficulty": 4, "confidence": 2, "enjoyment": 5, "hardest_part": "比例"})
        self._run_task("imagine_animal", pid=pid, n_strokes=6,
                       self_report={"difficulty": 2, "confidence": 4, "enjoyment": 4})

        rep = self.c.get(f"/api/participants/{pid}/representation").json()
        self.assertFalse(rep["cold_start"])
        self.assertEqual(rep["n_tasks"], 2)
        self.assertEqual(len(rep["source_sessions"]), 2)
        self.assertEqual(rep["coverage"]["task_ids"], ["emotion_alone", "imagine_animal"])

        # process facts come off the event timeline, undo included
        first = rep["tasks"][0]["process"]
        self.assertEqual((first["strokes"], first["strokes_removed"]), (4, 1))
        self.assertEqual(first["zoom_max"], 4.0)
        self.assertEqual(first["longest_pause_ms"], 70000)
        self.assertTrue(rep["process"]["zoom_used"])
        self.assertEqual(rep["self_report"]["difficulty"], 3.0)     # (4 + 2) / 2
        self.assertEqual(rep["coverage"]["hardest_parts"], ["比例"])

    def test_representation_is_rebuilt_not_cached(self):
        """`before` reproduces the input a past decision had, at any later time."""
        pid = "P-REP-02"
        sid1, _, _ = self._run_task("emotion_alone", pid=pid)
        first_at = self.c.get(f"/api/sessions/{sid1}").json()["created_at"]
        self._run_task("imagine_animal", pid=pid)

        now = self.c.get(f"/api/participants/{pid}/representation").json()
        self.assertEqual(now["n_tasks"], 2)
        earlier = self.c.get(f"/api/participants/{pid}/representation",
                             params={"before": first_at}).json()
        self.assertEqual(earlier["n_tasks"], 0)
        self.assertTrue(earlier["cold_start"])
        # nothing was written to make either answer
        self.assertFalse((SESSIONS / sid1 / "representation.json").exists())

    def test_either_id_finds_the_same_child(self):
        pid = "P-REP-03"
        self._run_task("emotion_alone", pid=pid)
        by_code = self.c.get(f"/api/participants/{pid}/history").json()
        by_device = self.c.get("/api/participants/ /history", params={"anon_id": f"anon-{pid}"}).json()
        self.assertEqual(by_code["n_tasks"], 1)
        self.assertEqual(by_device["n_tasks"], 1)

        # a code narrows to that code: a shared device must not merge children
        other = self.c.get("/api/participants/P-REP-03-OTHER/history",
                           params={"anon_id": f"anon-{pid}"}).json()
        self.assertEqual(other["n_tasks"], 0)

    # -- the three arms -----------------------------------------------------
    def test_control_arm_is_shown_nothing_but_still_predicts(self):
        pid = "P-ARM-NONE"
        self._run_task("emotion_alone", pid=pid, self_report={"difficulty": 5, "confidence": 1})
        _, created, _ = self._run_task("imagine_animal", pid=pid, condition={"history_mode": "none"})
        p = created["personalization"]
        self.assertEqual((p["requested_mode"], p["backend"]), ("none", "none"))
        self.assertEqual(p["shown"], [])
        # it had a history available and did not look: that is the control
        self.assertEqual(p["history_used"]["n_tasks"], 0)

    def test_history_arm_shows_the_childs_own_record(self):
        pid = "P-ARM-HIST"
        self._run_task("emotion_alone", pid=pid,
                       self_report={"difficulty": 4, "confidence": 2, "hardest_part": "颜色"})
        sid, created, _ = self._run_task("imagine_animal", pid=pid, condition={"history_mode": "history"})
        p = created["personalization"]
        self.assertEqual((p["requested_mode"], p["backend"]), ("history", "own_history"))
        self.assertTrue(p["available"])
        self.assertEqual(p["history_used"]["n_tasks"], 1)
        self.assertTrue(p["shown"])
        self.assertIn("颜色", " ".join(l["text"] for l in p["shown"]))

        frozen = self.c.get(f"/api/sessions/{sid}/personalization").json()
        self.assertEqual(frozen["representation"]["n_tasks"], 1)     # the exact input, kept
        self.assertIn("difficulty", frozen["prediction"])
        self.assertTrue(any(e["type"] == "HISTORY_SHOWN"
                            for e in self.c.get(f"/api/sessions/{sid}").json()["events"]))

    def test_a_downgraded_arm_is_never_silent(self):
        """Requesting the model arm without a model must not look like `history`."""
        p = get_personalizer("personalized").prepare({"difficulty": 3}, {"cold_start": True})
        self.assertEqual(p["requested_mode"], "personalized")
        self.assertEqual(p["backend"], "own_history")
        self.assertFalse(p["available"])
        self.assertIn("no model backend", p["note"])

    # -- prediction → self-report ------------------------------------------
    def test_prediction_is_scored_against_the_self_report(self):
        pid = "P-PRED"
        self._run_task("emotion_alone", pid=pid, self_report={"difficulty": 4, "confidence": 2})
        sid, created, q = self._run_task(
            "imagine_animal", pid=pid, condition={"history_mode": "history"},
            self_report={"difficulty": 3, "confidence": 4})

        predicted = created["personalization"]
        self.assertTrue(predicted["available"])
        rec = self.c.get(f"/api/sessions/{sid}/personalization").json()
        self.assertEqual(rec["outcome"], {"difficulty": 3, "confidence": 4})
        # error is (predicted - actual), computed from the number frozen before drawing
        self.assertAlmostEqual(rec["error"]["difficulty"],
                               rec["prediction"]["difficulty"] - 3, places=3)
        self.assertEqual(q["prediction_error"], rec["error"])

    def test_export_carries_the_arm_comparison(self):
        pid = "P-EXPORT"
        self._run_task("emotion_alone", pid=pid, self_report={"difficulty": 4, "confidence": 2})
        self._run_task("imagine_animal", pid=pid, condition={"history_mode": "history"},
                       self_report={"difficulty": 3, "confidence": 4})
        import tempfile
        out = Path(tempfile.mkdtemp(prefix="artquest-pz-"))
        counts = export(out)
        self.assertGreaterEqual(counts["personalization"], 2)
        rows = (out / "personalization.csv").read_text(encoding="utf-8").splitlines()
        head = rows[0].split(",")
        for col in ("requested_mode", "backend", "n_prior_tasks",
                    "pred_difficulty", "actual_difficulty", "abs_err_difficulty"):
            self.assertIn(col, head)
        self.assertIn("cond_history_mode", (out / "sessions.csv").read_text(encoding="utf-8").splitlines()[0])


if __name__ == "__main__":
    unittest.main()
