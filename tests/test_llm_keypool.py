"""多把 key 轮着用（网关的并发闸按 key 开，几把 key 就是几倍通道）。不打真接口：假 httpx.post。

守三件事：
1. 逗号分隔的 key 拆成几把；每把各自一条队，挑在飞最少的那把。
2. 一把 key 撞上 429，退避后换另一把重试，不在同一把上死磕。
3. 日志和体检单里只有 key 的编号和数量，没有 key 本身。

Run:  python3 -m unittest -v
"""
import importlib
import os
import threading
import time
import unittest
from unittest import mock

from .env import TMP as _TMP  # noqa: F401

ENV = {"ARTQUEST_LLM_BASE_URL": "https://chat.ecnu.edu.cn/open/api/v1",
       "ARTQUEST_LLM_API_KEY": "sk-aaa, sk-bbb ,sk-ccc", "ARTQUEST_MODEL": "ecnu-plus", "ARTQUEST_LLM_CONCURRENCY": "1"}


class _Resp:
    def __init__(self, status, text="通"):
        self.status_code = status; self.text = text; self._t = text
    def json(self): return {"choices": [{"message": {"content": self._t}, "finish_reason": "stop"}], "usage": {}}


def _reload():
    import artquest.config, artquest.llm
    importlib.reload(artquest.config); importlib.reload(artquest.llm)
    return artquest.config, artquest.llm


class KeyPool(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV); self.env.start()
        self.cfg, self.llm = _reload()

    def tearDown(self):
        self.env.stop(); _reload()

    def test_keys_are_split_and_trimmed(self):
        self.assertEqual(self.cfg.LLM_API_KEYS, ["sk-aaa", "sk-bbb", "sk-ccc"])
        self.assertEqual(self.cfg.LLM_API_KEY, "sk-aaa")
        self.assertTrue(self.cfg.llm_available())
        self.assertEqual(len(self.llm._POOL.keys), 3)

    def test_each_key_has_its_own_lane_and_the_emptiest_is_picked(self):
        """每把 1 路：三个并发请求应该三把 key 各用一次，第四个要等有人还回来。"""
        used, gate = [], threading.Event()
        def fake_post(url, json=None, headers=None, **k):
            used.append(headers["Authorization"].split()[1]); gate.wait(2); return _Resp(200)
        with mock.patch("httpx.post", fake_post):
            ts = [threading.Thread(target=lambda: self.llm.claude_text("", [{"type": "text", "text": "q"}])) for _ in range(3)]
            for t in ts: t.start()
            time.sleep(0.3)
            self.assertEqual(sorted(used), ["sk-aaa", "sk-bbb", "sk-ccc"], "三路同时在飞，三把 key 各占一条")
            self.assertEqual(self.llm._POOL.snapshot(), [1, 1, 1])
            gate.set()
            for t in ts: t.join(3)
        self.assertEqual(self.llm._POOL.snapshot(), [0, 0, 0], "用完都还回去了")

    def test_429_on_one_key_is_retried_on_another(self):
        seen = []
        def fake_post(url, json=None, headers=None, **k):
            key = headers["Authorization"].split()[1]; seen.append(key)
            return _Resp(429, '{"detail":{"type":"model_concurrency_exceeded"}}') if key == "sk-aaa" else _Resp(200)
        with mock.patch("httpx.post", fake_post), mock.patch("artquest.llm.time.sleep", lambda s: None):
            out = self.llm.claude_text("", [{"type": "text", "text": "q"}])
        self.assertEqual(out, "通")
        self.assertEqual(seen[0], "sk-aaa")
        self.assertNotEqual(seen[-1], "sk-aaa", "第二次换了一把 key")
        self.assertIn("sk-aaa", seen); self.assertLessEqual(len(seen), 3)

    def test_keys_never_appear_in_the_log_or_the_stats(self):
        with mock.patch("httpx.post", lambda *a, **k: _Resp(200)), self.assertLogs("artquest", level="INFO") as cm:
            self.llm.claude_text("", [{"type": "text", "text": "q"}])
        joined = "\n".join(cm.output)
        for key in ("sk-aaa", "sk-bbb", "sk-ccc"):
            self.assertNotIn(key, joined); self.assertNotIn(key, str(self.llm.LAST_CALL))
        self.assertEqual(self.llm.LAST_CALL["keys"], 3)
