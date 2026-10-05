"""英文会话下，反馈 / 陪伴 / 离线评分说英文；中文会话一个字不变。

语言从 `quest["lang"]` 上读：main.py 在英文会话里传一份英文任务（带 `lang: "en"`），
中文任务没有这个字段。三条引擎都不改签名。

Run:  python3 -m unittest -v
"""
import io
import re
import unittest

from .env import TMP as _TMP  # noqa: F401  (offline backends, throwaway data dir)

from PIL import Image, ImageDraw  # noqa: E402

from artquest.assist.template_assist import TemplateAssist, bare_intent  # noqa: E402
from artquest.feedback.template_feedback import TemplateFeedback  # noqa: E402
from artquest.scoring.heuristic_scorer import HeuristicScorer  # noqa: E402

CJK = re.compile(r"[㐀-鿿　-〿＀-￯]")
ZH_QUEST = {"title": "x", "prompt": "y", "focus_dims": ["imagination", "color_richness"]}
EN_QUEST = dict(ZH_QUEST, lang="en")
SCORES = {"dims": {"imagination": {"score": 2}, "color_richness": {"score": 4}}}


def _png():
    img = Image.new("RGB", (200, 200), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((30, 30, 120, 120), fill=(240, 80, 40))
    d.line((10, 190, 190, 20), fill=(20, 60, 200), width=4)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return buf.getvalue()


class EnglishEngines(unittest.TestCase):
    def test_feedback_speaks_english_with_the_three_fixed_openers(self):
        intent = {"text": "a cat sleeping in a tree", "emotion": "开心"}
        text = TemplateFeedback().feedback(b"", EN_QUEST, intent, SCORES)["text"]
        self.assertIsNone(CJK.search(text), text)
        for opener in ("I see:", "One question:", "Try this:"):
            self.assertIn(opener, text)
        self.assertIn("happy", text, "中文心情词要换成英文说出来")
        cmp = TemplateFeedback().compare(b"", b"", SCORES, {"dims": {"imagination": {"score": 3.5}, "color_richness": {"score": 4}}},
                                         EN_QUEST, intent)["text"]
        self.assertIsNone(CJK.search(cmp), cmp)
        self.assertIn("imagination", cmp)

    def test_chinese_feedback_is_untouched(self):
        intent = {"text": "一只在树上睡觉的猫", "emotion": "开心"}
        text = TemplateFeedback().feedback(b"", ZH_QUEST, intent, SCORES)["text"]
        self.assertTrue(text.startswith("我看到：你选的心情是「开心」，想画的是「一只在树上睡觉的猫」。"), text)
        self.assertIn("和「想象」有关的地方", text)

    def test_empty_intent_leaves_no_empty_quotes_and_simple_mode_is_short(self):
        """心情、心愿没填就不提；简单版只要「我看到」+「可以试试」，中英都不超过一口气。"""
        eng = TemplateFeedback()
        for quest in (ZH_QUEST, EN_QUEST):
            text = eng.feedback(b"", quest, {"text": "", "emotion": ""}, SCORES)["text"]
            self.assertNotIn("「」", text); self.assertNotIn("\u201c\u201d", text); self.assertNotIn("——", text)
            simple = eng.feedback(b"", dict(quest, ui="simple"), {"text": "", "emotion": ""}, SCORES)["text"]
            self.assertEqual(simple.count("\n"), 0, simple)          # 简单版：一句话
            self.assertNotIn("一个问题" if quest is ZH_QUEST else "One question", simple)
            limit = 20 if quest is ZH_QUEST else 12
            size = len(simple) if quest is ZH_QUEST else len(simple.split())
            self.assertLessEqual(size, limit, simple)
            cmp = eng.compare(b"", b"", SCORES, SCORES, dict(quest, ui="simple"), {})["text"]
            self.assertNotIn("？", cmp); self.assertNotIn("?", cmp)
        # 简单版的陪伴：每句更短
        for quest in (ZH_QUEST, EN_QUEST):
            for n in range(1, 7):
                t = TemplateAssist().assist(b"", dict(quest, ui="simple"), {"text": "", "emotion": ""}, nth=n)["text"]
                self.assertLessEqual(len(t) if quest is ZH_QUEST else len(t.split()), 12 if quest is ZH_QUEST else 8, t)

    def test_assist_speaks_english_and_gives_the_intent_back_without_its_lead_in(self):
        eng = TemplateAssist()
        intent = {"text": "I want to draw a quiet room.", "emotion": "平静"}
        texts = [eng.assist(b"", EN_QUEST, intent, nth=n)["text"] for n in range(1, 13)]
        for t in texts:
            self.assertIsNone(CJK.search(t), t)
        quoted = [t for t in texts if "a quiet room" in t]
        self.assertTrue(quoted, "意图从来没有被还给孩子")
        for t in quoted:
            self.assertNotIn("I want to draw", t, t)
            self.assertNotIn("room.", t, t)
        self.assertNotIn("quiet room", texts[0], "第一句不复读意图")
        self.assertEqual(len(set(texts[:6])), 6, "前六句不该重复")

    def test_assist_never_judges_in_english_either(self):
        forbidden = ("composition", "perspective", "shading", "should", "try to", "great job", "well done",
                     "too ", "not enough", "better")
        eng = TemplateAssist()
        for n in range(1, 13):
            t = eng.assist(b"", EN_QUEST, {"text": "a cat", "emotion": "开心"}, nth=n)["text"].lower()
            for w in forbidden:
                self.assertNotIn(w, t, f"第 {n} 句越界了（{w}）：{t}")

    def test_bare_intent_handles_both_languages(self):
        self.assertEqual(bare_intent("我想画一个安静的房间。"), "一个安静的房间")
        self.assertEqual(bare_intent("I want to draw a quiet room."), "a quiet room")
        self.assertEqual(bare_intent("Draw a dragon!"), "a dragon")
        self.assertEqual(bare_intent("a dragon"), "a dragon")

    def test_heuristic_notes_are_english_and_numbers_are_identical(self):
        png = _png()
        zh = HeuristicScorer().score(png, ZH_QUEST, {})
        en = HeuristicScorer().score(png, EN_QUEST, {})
        for k in zh["dims"]:
            self.assertEqual(zh["dims"][k]["score"], en["dims"][k]["score"], k)
            self.assertIsNone(CJK.search(en["dims"][k]["note"]), en["dims"][k]["note"])
        self.assertIsNone(CJK.search(en["summary"]), en["summary"])
        self.assertEqual(zh["dims"]["realism"]["note"], "启发式无法判断（需模型评分）")
        self.assertEqual(en["dims"]["realism"]["note"], "Not measured offline")


if __name__ == "__main__":
    unittest.main()
