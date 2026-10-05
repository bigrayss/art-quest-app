"""OpenAI 兼容通路（ecnu-plus）。不打真接口：把 httpx.post 换成假的，看请求长什么样、回复怎么解析。

守三件事：
1. 图片块要翻成 data URL 的 image_url，system 要进 messages[0]，key 要进 Authorization。
2. 没有 json_schema 的服务，JSON 得从散文里捞出来、按 schema 校验，少一个维度就不收。
3. 四个引擎报的 backend 名字跟提供方走（记录里得看得出是谁答的）。

Run:  python3 -m unittest -v
"""
import importlib
import json
import os
import unittest
from unittest import mock

from .env import TMP as _TMP  # noqa: F401  offline backends + throwaway data dir

ECNU = {"ARTQUEST_LLM_BASE_URL": "https://chat.ecnu.edu.cn/open/api/v1",
        "ARTQUEST_LLM_API_KEY": "sk-test", "ARTQUEST_MODEL": "ecnu-plus"}


def _reload_openai():
    import artquest.config, artquest.llm
    importlib.reload(artquest.config)
    importlib.reload(artquest.llm)
    return artquest.config, artquest.llm


class _Resp:
    def __init__(self, text, status=200):
        self.status_code = status
        self._text = text
        self.text = text if isinstance(text, str) else json.dumps(text)

    def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": self._text}}]}


class ProviderSelection(unittest.TestCase):
    def test_base_url_plus_key_selects_openai_and_names_backend_ecnu(self):
        with mock.patch.dict(os.environ, ECNU):
            cfg, _ = _reload_openai()
            self.assertEqual(cfg.LLM_PROVIDER, "openai")
            self.assertEqual(cfg.LLM_BACKEND, "ecnu")
            self.assertEqual(cfg.LLM_MODEL, "ecnu-plus")
            self.assertTrue(cfg.llm_available())
            # 老 .env 写的 claude，照样当「用模型」
            self.assertEqual(cfg.resolve_backend("claude", "claude", "heuristic"), "claude")
            self.assertEqual(cfg.resolve_backend("llm", "claude", "template"), "claude")
            self.assertEqual(cfg.resolve_backend("heuristic", "claude", "heuristic"), "heuristic")
        _reload_openai()

    def test_no_keys_means_offline(self):
        env = {k: "" for k in ECNU} | {"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": ""}
        with mock.patch.dict(os.environ, env):
            cfg, _ = _reload_openai()
            self.assertEqual(cfg.LLM_PROVIDER, "anthropic")
            self.assertFalse(cfg.llm_available())
            self.assertEqual(cfg.resolve_backend("auto", "claude", "template"), "template")
        _reload_openai()


class OpenAIRequestShape(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ECNU)
        self.env.start()
        self.cfg, self.llm = _reload_openai()

    def tearDown(self):
        self.env.stop()
        _reload_openai()

    def test_image_block_becomes_data_url_and_key_goes_in_header(self):
        seen = {}

        def fake_post(url, json=None, timeout=None, headers=None):
            seen.update(url=url, body=json, headers=headers)
            return _Resp("你画了一个圆。")

        with mock.patch("httpx.post", fake_post):
            out = self.llm.claude_text("系统话", [self.llm.image_block(b"\x89PNG"), {"type": "text", "text": "问"}], 50)
        self.assertEqual(out, "你画了一个圆。")
        self.assertEqual(seen["url"], "https://chat.ecnu.edu.cn/open/api/v1/chat/completions")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer sk-test")
        body = seen["body"]
        self.assertEqual(body["model"], "ecnu-plus")
        self.assertEqual(body["messages"][0], {"role": "system", "content": "系统话"})
        user = body["messages"][1]["content"]
        self.assertEqual(user[0]["type"], "image_url")
        self.assertTrue(user[0]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(user[1], {"type": "text", "text": "问"})
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertNotIn("reasoning_effort", body)

    def test_think_tags_and_reasoning_content_never_reach_the_child(self):
        with mock.patch("httpx.post", lambda *a, **k: _Resp("<think>先想想</think>它有三只眼睛。")):
            self.assertEqual(self.llm.claude_text("s", [{"type": "text", "text": "q"}]), "它有三只眼睛。")

    def test_http_error_raises_with_status(self):
        with mock.patch("httpx.post", lambda *a, **k: _Resp('{"detail":"token 无效或已过期"}', 401)):
            with self.assertRaises(RuntimeError) as cm:
                self.llm.claude_text("s", [{"type": "text", "text": "q"}])
        self.assertIn("401", str(cm.exception))


class JSONWithoutSchemaMode(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ECNU)
        self.env.start()
        self.cfg, self.llm = _reload_openai()
        from artquest.scoring.claude_scorer import _schema
        self.schema = _schema(["color_contrast", "line_combination"])

    def tearDown(self):
        self.env.stop()
        _reload_openai()

    def test_fenced_json_is_parsed_and_extra_keys_dropped(self):
        reply = "```json\n" + json.dumps({"dims": {"color_contrast": {"score": 3, "note": "黄蓝对比"},
                                                   "line_combination": {"score": 2.5, "note": "两条线", "extra": 1}},
                                          "summary": "一个圆一条线", "junk": True}, ensure_ascii=False) + "\n```"
        with mock.patch("httpx.post", lambda *a, **k: _Resp(reply)):
            out = self.llm.claude_json("评分", [{"type": "text", "text": "x"}], self.schema)
        self.assertEqual(set(out), {"dims", "summary"})
        self.assertEqual(out["dims"]["line_combination"], {"score": 2.5, "note": "两条线"})

    def test_schema_goes_into_system_prompt(self):
        seen = {}

        def fake_post(url, json=None, **k):
            seen["body"] = json
            return _Resp('{"dims":{"color_contrast":{"score":3,"note":"a"},"line_combination":{"score":3,"note":"b"}},"summary":"s"}')

        with mock.patch("httpx.post", fake_post):
            self.llm.claude_json("评分规则", [{"type": "text", "text": "x"}], self.schema)
        sys_msg = seen["body"]["messages"][0]["content"]
        self.assertTrue(sys_msg.startswith("评分规则"))
        self.assertIn('"line_combination"', sys_msg)

    def test_missing_dimension_is_rejected_after_one_retry(self):
        calls = []

        def fake_post(url, json=None, **k):
            calls.append(1)
            return _Resp('{"dims":{"color_contrast":{"score":3,"note":"a"}},"summary":"s"}')

        with mock.patch("httpx.post", fake_post):
            with self.assertRaises(self.llm.LLMBadOutput):
                self.llm.claude_json("评分", [{"type": "text", "text": "x"}], self.schema)
        self.assertEqual(len(calls), 2)

    def test_prose_then_json_on_retry_succeeds(self):
        replies = iter(["我觉得这幅画……", '{"dims":{"color_contrast":{"score":4,"note":"a"},"line_combination":{"score":3,"note":"b"}},"summary":"s"}'])
        with mock.patch("httpx.post", lambda *a, **k: _Resp(next(replies))):
            out = self.llm.claude_json("评分", [{"type": "text", "text": "x"}], self.schema)
        self.assertEqual(out["dims"]["color_contrast"]["score"], 4)


class EnginesReportTheProvider(unittest.TestCase):
    def test_backend_name_is_ecnu_and_prompts_are_unchanged(self):
        with mock.patch.dict(os.environ, ECNU | {"ARTQUEST_SCORER": "llm", "ARTQUEST_FEEDBACK": "llm"}):
            cfg, llm = _reload_openai()
            import artquest.scoring.claude_scorer as sc, artquest.feedback.claude_feedback as fb, artquest.assist.claude_assist as asst
            import artquest.scoring, artquest.feedback, artquest.assist
            # 包的 __init__ 在自己被 import 时就把 ARTQUEST_SCORER/FEEDBACK 读死了，得一起重载
            pkgs = (sc, fb, asst, artquest.scoring, artquest.feedback, artquest.assist)
            for m in pkgs:
                importlib.reload(m)
            self.assertEqual(sc.ClaudeScorer().name, "ecnu")
            self.assertEqual(fb.ClaudeFeedback().name, "ecnu")
            self.assertEqual(asst.ClaudeAssist().backend, "ecnu")
            from artquest.scoring import get_scorer
            from artquest.feedback import get_feedback_engine
            from artquest.assist import get_assist_engine
            with mock.patch("httpx.post", lambda *a, **k: _Resp("你给它画了三只眼睛。")):
                out = get_assist_engine().assist(b"\x89PNG", {"title": "t", "prompt": "p", "lang": "zh"}, {"text": "我想画猫"}, 1)
            self.assertEqual(out, {"text": "你给它画了三只眼睛。", "backend": "ecnu"})
            self.assertEqual(get_scorer().name, "ecnu")
            self.assertEqual(get_feedback_engine().name, "ecnu")
        cfg, llm = _reload_openai()
        for m in pkgs:           # 放回离线：后面的测试模块靠 heuristic/template
            importlib.reload(m)
