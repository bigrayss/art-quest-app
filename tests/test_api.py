"""End-to-end test of the Stage 1 loop with the offline backends.

Run:  python3 -m unittest -v
"""
import base64
import io
import os
import re
import unittest
from pathlib import Path

from .env import TMP as _TMP  # sets the offline backends and the test data dir

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

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
        self.assertEqual(len(s["snapshots"]), 1)   # 周期快照默认关，这里是测试显式打开的
        self.assertTrue(any(e["type"] == "FEEDBACK_SHOW" for e in s["events"]))

        # 四个数据文件 + 一张作品；修改前的那一张只有真的改过才存
        d = os.path.join(_TMP, "sessions", sid)
        for f in ("session.json", "final.png", "events.jsonl",
                  "checkpoints/before_feedback.png", "checkpoints/0001_45s.png"):
            self.assertTrue(os.path.exists(os.path.join(d, f)), f)
        for gone in ("metadata.json", "condition.json", "feedback.jsonl", "before.png", "after.png"):
            self.assertFalse(os.path.exists(os.path.join(d, gone)), gone)
        # 「阶段」不是文件名：这些 URL 照样解析得到
        for phase in ("before", "after", "final"):
            self.assertEqual(self.c.get(f"/files/{sid}/{phase}.png").status_code, 200, phase)

    def test_finalize_without_revision(self):
        sid = self.c.post("/api/sessions", json={"quest_id": "emotion_alone", "intent": {"emotion": "平静", "text": ""}}).json()["session_id"]
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 1}).status_code, 409)
        self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(), "elapsed_ms": 60000, "phase": "before"})
        s = self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 70000}).json()["session"]
        self.assertEqual(s["status"], "done")
        self.assertFalse(s["revised"])
        self.assertIn(sid, [x["session_id"] for x in self.c.get("/api/sessions").json()])

    def test_bad_inputs(self):
        self.assertEqual(self.c.post("/api/sessions", json={"quest_id": "nope", "intent": {"emotion": "x"}}).status_code, 400)
        self.assertEqual(self.c.get("/api/sessions/deadbeef0000").status_code, 404)
        sid = self.c.post("/api/sessions", json={"quest_id": "story_character_home", "intent": {"emotion": "x"}}).json()["session_id"]
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/snapshot", json={"image": "not-an-image", "elapsed_ms": 1}).status_code, 400)


class OneServerManyChildren(unittest.TestCase):
    """把服务器放到局域网上就不止一个孩子了。

    「画廊」「小传」「地图上的星」读的都是同一条 `/api/sessions`。
    不带身份问，它返回服务器上所有人的作品——别人的画会直接出现在这个孩子的
    个人页里，绕过了整套同意机制。所以 app 永远带着自己的两个 id 问。
    """
    def setUp(self):
        self.c = TestClient(app)

    def _session(self, anon, pid=""):
        return self.c.post("/api/sessions", json={
            "task_id": "M9_A", "intent": {"emotion": "好奇", "text": ""},
            "participant": {"anon_id": anon, "participant_id": pid},
            "canvas": {"width": 1024, "height": 704}}).json()["session_id"]

    def test_a_child_only_sees_their_own(self):
        mine = self._session("anon-mine-1", "P-MINE")
        theirs = self._session("anon-theirs-1", "P-THEIRS")

        got = [r["session_id"] for r in
               self.c.get("/api/sessions?anon_id=anon-mine-1&participant_id=P-MINE").json()]
        self.assertIn(mine, got)
        self.assertNotIn(theirs, got, "别人的作品不能出现在「我的」里")

        # 没有研究员编号的设备，只靠设备 id 也要认得出自己
        solo = self._session("anon-solo-1")
        got = [r["session_id"] for r in self.c.get("/api/sessions?anon_id=anon-solo-1").json()]
        self.assertEqual(got, [solo])

        # 不带参数仍然是研究员的全量视图（导出、教师端靠它）
        everything = [r["session_id"] for r in self.c.get("/api/sessions").json()]
        self.assertIn(mine, everything)
        self.assertIn(theirs, everything)


class FrontEndTargetsRealBrowsers(unittest.TestCase):
    """CSS the target browser does not know is dropped *silently*.

    This bit for real: `color-mix()` needs Chrome 111, the machine this is
    developed on runs 106, and one unsupported function voids the **whole**
    declaration — so the map's clay edges and the world's sky simply were not
    painted, with nothing in the console to say so. Blends are computed in JS
    now (`mixHex`) and written out as plain hex.

    `dvh` (Chrome 108) is allowed, but only with a `vh` line in front of it.
    """

    def _css(self):
        return (Path(__file__).resolve().parent.parent / "static" / "style.css").read_text(encoding="utf-8")

    @staticmethod
    def _uncommented(text):
        """Source with comments removed — they are allowed to name the hazard."""
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.sub(r"^\s*//.*$|(?<=[\s;{])//.*$", "", text, flags=re.M)

    def test_no_color_mix_anywhere_in_the_front_end(self):
        static = Path(__file__).resolve().parent.parent / "static"
        for f in ("style.css", "app.js", "index.html"):
            self.assertNotIn("color-mix(", self._uncommented((static / f).read_text(encoding="utf-8")),
                             f"{f}: color-mix() is dropped whole on Chrome < 111 — compute the blend instead")

    def test_every_dvh_has_a_vh_fallback(self):
        css = self._css()
        self.assertGreaterEqual(css.count("100vh"), css.count("100dvh"),
                                "each `100dvh` needs a `100vh` line before it (dvh is Chrome 108+)")


if __name__ == "__main__":
    unittest.main()
