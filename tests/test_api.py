"""End-to-end test of the Stage 1 loop with the offline backends.

Run:  python3 -m unittest -v
"""
import base64
import io
import os
import tempfile
import unittest

os.environ["ARTQUEST_SCORER"] = "heuristic"
os.environ["ARTQUEST_FEEDBACK"] = "template"
_TMP = tempfile.mkdtemp(prefix="artquest-test-")
os.environ["ARTQUEST_DATA_DIR"] = _TMP

import importlib  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

# unittest discovery may import artquest sub-packages (and thus config) before
# the env vars above are set — reload so the test data dir is honoured.
import artquest.config  # noqa: E402
importlib.reload(artquest.config)
from artquest.main import app  # noqa: E402


def _data_url(color=(200, 40, 40)):
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((50, 50, 250, 250), fill=color, outline="black", width=4)
    d.line((0, 290, 400, 200), fill=(30, 60, 200), width=6)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class StageOneLoop(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def test_config_and_quests(self):
        cfg = self.c.get("/api/config").json()
        self.assertEqual(cfg["scorer"], "heuristic")
        self.assertEqual(len(cfg["dimensions"]), 9)
        self.assertGreaterEqual(len(self.c.get("/api/quests").json()), 3)

    def test_full_loop_with_revision(self):
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "开心", "text": "一只会飞的鱼"}})
        self.assertEqual(r.status_code, 201)
        sid = r.json()["session_id"]

        r = self.c.post(f"/api/sessions/{sid}/snapshot", json={"image": _data_url(), "elapsed_ms": 45000,
                                                              "events": [{"t_ms": 1000, "type": "tool", "detail": {"tool": "pencil"}}]})
        self.assertTrue(r.json()["ok"])

        r = self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(), "elapsed_ms": 90000, "phase": "before"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["scores"]["dims"]), 9)
        self.assertIn("我看到", body["feedback"]["text"])

        # cannot submit before twice
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(), "elapsed_ms": 1, "phase": "before"}).status_code, 409)

        r = self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url((40, 200, 90)), "elapsed_ms": 150000, "phase": "after"})
        self.assertEqual(r.status_code, 200, r.text)
        s = r.json()["session"]
        self.assertEqual(s["status"], "done")
        self.assertTrue(s["revised"])
        self.assertEqual(len(s["snapshots"]), 1)
        self.assertTrue(any(e["type"] == "feedback_shown" for e in s["events"]))

        d = os.path.join(_TMP, "sessions", sid)
        for f in ("session.json", "before.png", "after.png", "snapshots/0001_45s.png"):
            self.assertTrue(os.path.exists(os.path.join(d, f)), f)
        self.assertEqual(self.c.get(f"/files/{sid}/before.png").status_code, 200)

    def test_finalize_without_revision(self):
        sid = self.c.post("/api/sessions", json={"quest_id": "emotion_alone", "intent": {"emotion": "平静", "text": ""}}).json()["session_id"]
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 1}).status_code, 409)
        self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(), "elapsed_ms": 60000, "phase": "before"})
        s = self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 70000}).json()["session"]
        self.assertEqual(s["status"], "done")
        self.assertFalse(s["revised"])
        self.assertIn(sid, [x["id"] for x in self.c.get("/api/sessions").json()])

    def test_bad_inputs(self):
        self.assertEqual(self.c.post("/api/sessions", json={"quest_id": "nope", "intent": {"emotion": "x"}}).status_code, 400)
        self.assertEqual(self.c.get("/api/sessions/deadbeef0000").status_code, 404)
        sid = self.c.post("/api/sessions", json={"quest_id": "story_character_home", "intent": {"emotion": "x"}}).json()["session_id"]
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/snapshot", json={"image": "not-an-image", "elapsed_ms": 1}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
