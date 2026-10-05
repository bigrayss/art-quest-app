"""v0.3 提示词（docs/art_feedback_prompts_zh_en_v0.3.json）接进三个模型引擎。不打真接口：假 httpx.post。

守四件事：
1. 打分一次一个维度、system 原文不拼、只问任务能考察的维度、回复里捞出 1–5。
2. 陪伴 / 评价 / 收尾三段 system 是文件里的原文，一字不加。
3. user 消息里有任务、想法、心情、分数和输出语言；考不到的维度写明不给数。
4. 英文会话用英文那套，中文用中文那套；打分量规默认英文（研究量表只用一份）。

Run:  python3 -m unittest -v
"""
import importlib
import json
import os
import unittest
from unittest import mock

from .env import TMP as _TMP  # noqa: F401

ECNU = {"ARTQUEST_LLM_BASE_URL": "https://chat.ecnu.edu.cn/open/api/v1",
        "ARTQUEST_LLM_API_KEY": "sk-test", "ARTQUEST_MODEL": "ecnu-plus"}
PROMPTS = json.load(open(os.path.join(os.path.dirname(__file__), "..", "artquest", "prompts", "art_feedback_v0.3.json"), encoding="utf-8"))


class _Resp:
    status_code = 200
    def __init__(self, text): self._t = text; self.text = text
    def json(self): return {"choices": [{"message": {"content": self._t}, "finish_reason": "stop"}], "usage": {}}


def _reload():
    import artquest.config, artquest.llm, artquest.scoring.claude_scorer, artquest.feedback.claude_feedback, artquest.assist.claude_assist
    for m in (artquest.config, artquest.llm, artquest.scoring.claude_scorer, artquest.feedback.claude_feedback, artquest.assist.claude_assist):
        importlib.reload(m)
    return artquest.scoring.claude_scorer, artquest.feedback.claude_feedback, artquest.assist.claude_assist


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ECNU); self.env.start()
        self.sc, self.fb, self.asst = _reload()
        self.calls = []

    def tearDown(self):
        self.env.stop(); _reload()

    def fake(self, reply):
        def post(url, json=None, **k):
            self.calls.append(json); return _Resp(reply() if callable(reply) else reply)
        return post

    @staticmethod
    def user_text(body):
        return "\n".join(p["text"] for p in body["messages"][-1]["content"] if p["type"] == "text")

    @staticmethod
    def system_of(body):
        return body["messages"][0]["content"] if body["messages"][0]["role"] == "system" else ""


class ScoringOneDimensionAtATime(Base):
    def test_only_applicable_dims_each_with_its_own_rubric_and_no_system(self):
        quest = {"title": "t", "prompt": "p", "applicable_dims": ["color_contrast", "line_combination", "imagination"]}
        with mock.patch("httpx.post", self.fake("4")):
            out = self.sc.ClaudeScorer().score(b"\x89PNG", quest, {})
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(set(out["dims"]), {"color_contrast", "line_combination", "imagination"})
        self.assertEqual(out["dims"]["imagination"], {"score": 4, "note": ""})
        self.assertEqual(out["prompt_version"], "art_feedback_v0.3")
        for body in self.calls:
            self.assertEqual(body["messages"][0]["role"], "user", "打分没有 system，量规整段在 user 里")
            text = self.user_text(body)
            self.assertFalse(text.startswith("<image>"))
            self.assertTrue(text.startswith("Assess the student's artwork based on the '"), text[:60])
            self.assertEqual(body["messages"][0]["content"][0]["type"], "image_url")
        rubrics = {self.user_text(b) for b in self.calls}
        self.assertEqual(rubrics, {PROMPTS["en"]["score"][k].replace("<image>", "", 1) for k in quest["applicable_dims"]})

    def test_digit_is_fished_out_of_chatter_and_missing_dims_are_dropped(self):
        replies = iter(["Score: 3/5", "I think this is a solid 5.", "no number", "still nothing"])
        quest = {"title": "t", "prompt": "p", "applicable_dims": ["realism", "deformation", "imagination"]}
        with mock.patch("httpx.post", self.fake(lambda: next(replies, "2"))):
            with mock.patch("artquest.scoring.claude_scorer.ThreadPoolExecutor") as ex:   # 串行，让顺序可预测
                class Seq:
                    def __enter__(s): return s
                    def __exit__(s, *a): pass
                    def map(s, f, xs): return [f(x) for x in xs]
                ex.return_value = Seq()
                out = self.sc.ClaudeScorer().score(b"\x89PNG", quest, {})
        self.assertEqual(out["dims"]["realism"]["score"], 3)
        self.assertEqual(out["dims"]["deformation"]["score"], 5)
        self.assertNotIn("imagination", out["dims"], "两次都没数字：这一维不给数，不编")

    def test_chinese_rubric_when_asked(self):
        with mock.patch.dict(os.environ, {"ARTQUEST_SCORE_PROMPT_LANG": "zh"}):
            import artquest.prompts; importlib.reload(artquest.prompts); sc, _, _ = _reload()
            with mock.patch("httpx.post", self.fake("3")):
                sc.ClaudeScorer().score(b"\x89PNG", {"title": "t", "prompt": "p", "applicable_dims": ["realism"]}, {})
            self.assertTrue(self.user_text(self.calls[0]).startswith("请根据‘写实表现’标准"))
        importlib.reload(artquest.prompts); _reload()


class ReviewAndFinal(Base):
    SCORES = {"dims": {"imagination": {"score": 2}, "color_richness": {"score": 4},
                       "realism": {"score": None, "na": True, "note": "考不到"}}}

    def test_review_system_is_verbatim_and_user_carries_task_scores_language(self):
        quest = {"title": "海边的城堡", "prompt": "画一座城堡", "ui": "full"}
        with mock.patch("httpx.post", self.fake("你画的塔尖很高。")):
            out = self.fb.ClaudeFeedback().feedback(b"\x89PNG", quest, {"text": "我想画城堡", "emotion": "开心"}, self.SCORES)
        self.assertEqual(out, {"backend": "ecnu", "text": "你画的塔尖很高。"})
        body = self.calls[0]
        self.assertEqual(self.system_of(body), PROMPTS["zh"]["review"])
        u = self.user_text(body)
        for s in ("绘画任务：海边的城堡", "任务要求：画一座城堡", "学生写下的想法：我想画城堡", "学生画前的心情：开心",
                  "- 想象力：2", "- 色彩丰富性：4", "- 写实表现：本任务不考察", "输出语言：简体中文。"):
            self.assertIn(s, u)
        self.assertNotIn("简单版", u)
        self.assertEqual([p["type"] for p in body["messages"][-1]["content"]], ["text", "image_url", "text"])

    def test_english_session_uses_english_prompt_and_translated_mood(self):
        quest = {"title": "Castle", "prompt": "Draw a castle", "lang": "en", "ui": "simple"}
        with mock.patch("httpx.post", self.fake("Nice tower.")):
            self.fb.ClaudeFeedback().feedback(b"\x89PNG", quest, {"text": "a castle", "emotion": "开心"}, self.SCORES)
        body = self.calls[0]
        self.assertEqual(self.system_of(body), PROMPTS["en"]["review"])
        u = self.user_text(body)
        for s in ("Task: Castle", "How the learner felt before starting: happy", "- Imagination: 2",
                  "- Realism: not assessed for this task", "Output language: English.", "Simple version: one sentence"):
            self.assertIn(s, u)

    def test_final_gets_both_labelled_images(self):
        quest = {"title": "t", "prompt": "p"}
        with mock.patch("httpx.post", self.fake("塔尖比刚才高了。")):
            self.fb.ClaudeFeedback().compare(b"\x89A", b"\x89B", self.SCORES, self.SCORES, quest, {"text": "", "emotion": ""})
        body = self.calls[0]
        self.assertEqual(self.system_of(body), PROMPTS["zh"]["final"])
        parts = body["messages"][-1]["content"]
        self.assertEqual([p["type"] for p in parts], ["text", "image_url", "text", "image_url", "text"])
        self.assertEqual(parts[0]["text"], "修改前的作品：")
        self.assertEqual(parts[2]["text"], "最终作品：")
        self.assertIn("学生写下的想法：（没写）", parts[4]["text"])

    def test_no_scores_is_said_not_faked(self):
        with mock.patch("httpx.post", self.fake("x")):
            self.fb.ClaudeFeedback().feedback(b"\x89PNG", {"title": "t", "prompt": "p"}, {}, {"dims": {}})
        self.assertIn("九维评分：未提供。", self.user_text(self.calls[0]))


class DuringDrawing(Base):
    def test_during_system_is_verbatim_and_nth_is_passed(self):
        with mock.patch("httpx.post", self.fake("你给它画了三只眼睛。")):
            out = self.asst.ClaudeAssist().assist(b"\x89PNG", {"title": "t", "prompt": "p", "ui": "simple"}, {"text": "我想画猫", "emotion": "平静"}, nth=2)
        self.assertEqual(out, {"text": "你给它画了三只眼睛。", "backend": "ecnu"})
        body = self.calls[0]
        self.assertEqual(self.system_of(body), PROMPTS["zh"]["during"])
        u = self.user_text(body)
        self.assertIn("第 2 次点开你", u); self.assertIn("简单版：只说一句", u); self.assertIn("当前作品（还在画）：", u)

    def test_english_during(self):
        with mock.patch("httpx.post", self.fake("You gave it three eyes.")):
            self.asst.ClaudeAssist().assist(b"\x89PNG", {"title": "t", "prompt": "p", "lang": "en"}, {"text": "a cat", "emotion": ""}, nth=1)
        body = self.calls[0]
        self.assertEqual(self.system_of(body), PROMPTS["en"]["during"])
        self.assertIn("Output language: English.", self.user_text(body))
