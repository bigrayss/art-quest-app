"""一笔没画的空局不是作品（用户 2026-10-05：「空白的你还是放进了我的画作里」）。

1. 退出时一笔没画 → 这局直接删掉，不保存。
2. 直接关掉 app 没走退出流程留下的空局 → 孩子的画廊列表里不出现；研究员的全量视图照旧。
3. 画过哪怕一笔的没完成作品仍然挂在画廊里（半张画也是画过的证据）。

Run:  python3 -m unittest -v
"""
import unittest

from .env import TMP as _TMP, ADMIN  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402

from artquest.main import app  # noqa: E402

STROKE = {"seq": 1, "stroke_id": "s00001", "phase": "before", "t_start_ms": 900, "tool": "pencil",
          "color": "#222222", "size": 4, "opacity": 1.0,
          "points": [[100, 100, 0, None, None, None], [160, 140, 90, None, None, None]]}


class BlankSessions(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.anon = "blank-test-device"

    def _open(self):
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "平静", "text": ""},
                                               "participant": {"anon_id": self.anon}})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["session_id"]

    def _mine(self):
        return [r["session_id"] for r in self.c.get(f"/api/sessions?anon_id={self.anon}").json()]

    def test_leaving_without_a_single_stroke_deletes_the_session(self):
        sid = self._open()
        r = self.c.post(f"/api/sessions/{sid}/abandon", json={"elapsed_ms": 3000, "reason": "wrong_task"})
        self.assertEqual(r.json()["status"], "deleted")
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").status_code, 404)
        self.assertNotIn(sid, self._mine())

    def test_a_blank_session_left_open_is_hidden_from_the_child_but_not_the_researcher(self):
        sid = self._open()                       # 关掉 app 了，没有 abandon
        self.assertNotIn(sid, self._mine())
        everyone = [r["session_id"] for r in self.c.get("/api/sessions", headers=ADMIN).json()]
        self.assertIn(sid, everyone, "研究员的全量视图不藏")

    def test_one_stroke_is_enough_to_keep_an_unfinished_drawing(self):
        sid = self._open()
        self.c.post(f"/api/sessions/{sid}/log", json={"events": [], "strokes": [STROKE]})
        self.assertIn(sid, self._mine())
        r = self.c.post(f"/api/sessions/{sid}/abandon", json={"elapsed_ms": 5000, "reason": "wrong_task"})
        self.assertEqual(r.json()["status"], "abandoned")
        self.assertIn(sid, self._mine(), "画过一笔的没完成作品留着，只是标记")
