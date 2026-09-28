# -*- coding: utf-8 -*-
"""界面语言：英文会话从头到尾是英文，中文会话一个字节不变。

语言在建 session 的那一刻冻进 session。之后评分、反馈、陪伴都按它，不再看请求头——
孩子中途切了语言，这一次创作仍然只有一种语言。
"""
import base64
import io
import re
import unittest

from .env import ADMIN, TMP as _TMP  # noqa: F401  (offline backends, throwaway data dir)

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest.main import app  # noqa: E402

CJK = re.compile(r"[一-鿿「」，。：；！？（）]")


def _png():
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((50, 50, 250, 250), fill=(200, 40, 40), outline="black", width=4)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class EnglishSessions(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def test_quests_and_families_come_back_in_english_when_asked(self):
        zh = self.c.get("/api/quests").json()
        en = self.c.get("/api/quests", headers={"Accept-Language": "en-US,en;q=0.9"}).json()
        self.assertEqual([q["id"] for q in zh], [q["id"] for q in en], "id 和顺序不能因为语言而变")
        for q in en:
            for k in ("title", "instruction", "prompt", "hint", "family_name"):
                self.assertFalse(CJK.search(q[k] or ""), f"{q['id']}.{k} 还有中文：{q[k]!r}")
        self.assertTrue(all(CJK.search(q["title"]) for q in zh), "不带语言头就是中文")
        fams = self.c.get("/api/families?lang=en").json()
        self.assertTrue(fams and all(not CJK.search(f["name"]) for f in fams))

    def test_the_language_is_frozen_on_the_session_and_the_feedback_follows_it(self):
        r = self.c.post("/api/sessions", headers={"Accept-Language": "en"},
                        json={"quest_id": "imagine_animal", "intent": {"emotion": "开心", "text": "a flying fish"}})
        self.assertEqual(r.status_code, 201, r.text)
        sid = r.json()["session_id"]
        meta = self.c.get(f"/api/sessions/{sid}").json()
        self.assertEqual(meta["lang"], "en")
        self.assertFalse(CJK.search(meta["task"]["title"]), "task 快照记的是孩子看到的那一版")
        # 之后的请求哪怕不带语言头（或者带了中文），反馈仍然是英文
        r = self.c.post(f"/api/sessions/{sid}/submit", headers={"Accept-Language": "zh-CN"},
                        json={"image": _png(), "elapsed_ms": 90000, "phase": "before"})
        self.assertEqual(r.status_code, 200, r.text)
        fb = (r.json().get("feedback") or {}).get("text", "")
        self.assertTrue(fb, r.json())
        self.assertFalse(CJK.search(fb), fb)
        r = self.c.post(f"/api/sessions/{sid}/assist", json={"image": _png(), "nth": 1, "events": []})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(CJK.search(r.json()["text"]), r.json()["text"])

    def test_a_chinese_session_is_untouched(self):
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "开心", "text": "一只会飞的鱼"}})
        sid = r.json()["session_id"]
        meta = self.c.get(f"/api/sessions/{sid}").json()
        self.assertEqual(meta["lang"], "zh")
        self.assertTrue(CJK.search(meta["task"]["title"]))
        r = self.c.post(f"/api/sessions/{sid}/submit", json={"image": _png(), "elapsed_ms": 90000, "phase": "before"})
        self.assertTrue(CJK.search((r.json().get("feedback") or {}).get("text", "")))


if __name__ == "__main__":
    unittest.main()
