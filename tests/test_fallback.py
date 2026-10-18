"""模型挂了不给孩子看错误文字（2026-10-18，ecnu key 失效那几天的教训）。

配置的是模型引擎、模型答不了（这里：anthropic 通路没 key，连 client 都建不起来）→ 评分退回启发式、
反馈和对比退回模板，结果照常给孩子；记录里说清本来该谁答（fallback_from）、为什么没答（fallback_error），
时间线上一条 MODEL_FALLBACK。远程失败的记录照样一条条在，再加一条真正答了的本地执行。

Run:  python3 -m unittest -v tests.test_fallback
"""
import base64
import io
import unittest

from .env import TMP as _TMP  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import artquest.main as main_mod  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.storage import SessionStore  # noqa: E402


def _png(seed=0):
    img = Image.new("RGB", (320, 220), "white")
    ImageDraw.Draw(img).ellipse((40 + seed, 40, 220, 180), fill=(150, 190, 235), outline="black", width=4)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _stroke(i):
    return {"seq": i, "stroke_id": f"s{i:05d}", "phase": "before", "tool": "pen", "color": "#000000", "size": 4,
            "opacity": 1.0, "erase": False, "pointer_type": "pen", "t0_ms": 100 * i,
            "points": [[10 + i, 10, 0, None, None, None], [40 + i, 40, 30, None, None, None]]}


class ModelDownFallsBackToOfflineEngines(unittest.TestCase):
    def setUp(self):
        from artquest.scoring.claude_scorer import ClaudeScorer
        from artquest.feedback.claude_feedback import ClaudeFeedback
        self.saved = (main_mod.get_scorer, main_mod.get_feedback_engine)
        main_mod.get_scorer = lambda: ClaudeScorer()
        main_mod.get_feedback_engine = lambda: ClaudeFeedback()
        self.c = TestClient(app)
        self.store = SessionStore()

    def tearDown(self):
        main_mod.get_scorer, main_mod.get_feedback_engine = self.saved

    def test_scores_and_feedback_still_arrive_and_the_fallback_is_on_record(self):
        sid = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                                                 "participant": {"anon_id": "anon-fallback"}}).json()["session_id"]
        r = self.c.post(f"/api/sessions/{sid}/submit", json={"image": _png(), "elapsed_ms": 1000, "phase": "before", "strokes": [_stroke(1)]})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["scores"]["backend"], "heuristic", "评分退回启发式")
        self.assertTrue(body["scores"]["dims"], "有分数，不是空的")
        self.assertEqual(body["scores"]["fallback_from"], main_mod.LLM_BACKEND)
        self.assertEqual(body["feedback"]["backend"], "template", "反馈退回模板")
        self.assertNotIn("失败", body["feedback"]["text"])
        self.assertEqual(body["feedback"]["fallback_from"], main_mod.LLM_BACKEND)
        r = self.c.post(f"/api/sessions/{sid}/submit", json={"image": _png(3), "elapsed_ms": 5000, "phase": "after", "pending": 0})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["comparison"]["backend"], "template")
        self.assertNotIn("失败", r.json()["comparison"]["text"])

        m = self.store.load(sid)
        self.assertEqual(m["before"]["scores"]["backend"], "heuristic")
        self.assertEqual(m["after"]["scores"]["fallback_from"], main_mod.LLM_BACKEND)
        fb = self.store.feedback_log(sid)
        self.assertEqual([f["backend"] for f in fb], ["template", "template"])
        self.assertTrue(all(f["fallback_from"] == main_mod.LLM_BACKEND for f in fb))
        events = [e["payload"] for e in self.store.log(sid, "events").read() if e["type"] == "MODEL_FALLBACK"]
        self.assertEqual([e["purpose"] for e in events], ["score", "review", "score", "final"])
        self.assertTrue(all(e["from"] == main_mod.LLM_BACKEND and e["error"] for e in events))
        self.assertEqual({e["to"] for e in events}, {"heuristic", "template"})
        # 记录：远程失败的那些照样在（exception），每一步再加一条真正答了的 local，带 fallback_from / fallback_error
        calls = self.store.calls(sid)
        remote = [c for c in calls if c["execution_kind"] == "remote"]
        self.assertTrue(remote and all(c["outcome"] in ("exception", "http_error") for c in remote))
        local = [c for c in calls if c["execution_kind"] == "local" and c.get("fallback_from")]
        self.assertEqual([(c["purpose"], c["backend"]) for c in local],
                         [("score", "heuristic"), ("review", "template"), ("score", "heuristic"), ("final", "template")])
        self.assertTrue(all(c["outcome"] == "ok" and c["fallback_error"] for c in local))
        # 同一轮里远程失败和本地顶上是同一个 group
        for c in local:
            self.assertTrue(any(r_["group_id"] == c["group_id"] for r_ in remote), c["purpose"])


if __name__ == "__main__":
    unittest.main()
