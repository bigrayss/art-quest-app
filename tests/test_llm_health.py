"""模型健康那一行（2026-11-10）：key 过期是静默的（兜底把 401 吞掉给孩子模板），
所以 llm.py 记最近一次成败，/api/config 的 llm.health 把它交给「我的 → 这台设备」。

守三件事：
1. 401/403 → key_expired；超时/连不上 → unreachable；成功 → ok。since 只在状态变的时候动。
2. /api/config 里 llm.health 有 state/since，没有错误原文（接口是公开的）。
3. probe() 失败不抛，只更新状态。

Run:  python3 -m unittest -v tests.test_llm_health
"""
import os
import unittest
from unittest import mock

from .env import TMP as _TMP  # noqa: F401

from .test_llm_openai import ECNU, _Resp, _reload_openai  # noqa: E402


class HealthFollowsCalls(unittest.TestCase):
    def setUp(self):
        self.patched = mock.patch.dict(os.environ, ECNU)
        self.patched.start()
        self.cfg, self.llm = _reload_openai()
        self.llm.reset_health()

    def tearDown(self):
        self.patched.stop()
        _reload_openai()

    def ask(self):
        return self.llm.claude_text("s", [{"type": "text", "text": "q"}])

    def test_untested_then_expired_then_ok(self):
        self.assertEqual(self.llm.health()["state"], "untested")
        with mock.patch("httpx.post", lambda *a, **k: _Resp('{"detail":"token 无效或已过期"}', 401)):
            with self.assertRaises(RuntimeError):
                self.ask()
        h = self.llm.health()
        self.assertEqual(h["state"], "key_expired")
        self.assertEqual(h["http_status"], 401)
        self.assertTrue(h["since"] and h["fail_at"] and not h["ok_at"])
        since = h["since"]
        # 同一状态再失败一次，since 不动
        with mock.patch("httpx.post", lambda *a, **k: _Resp("nope", 403)):
            with self.assertRaises(RuntimeError):
                self.ask()
        self.assertEqual(self.llm.health()["since"], since)
        # 换了 key，第一次成功就翻回 ok
        with mock.patch("httpx.post", lambda *a, **k: _Resp("OK")):
            self.assertEqual(self.ask(), "OK")
        h = self.llm.health()
        self.assertEqual(h["state"], "ok")
        self.assertTrue(h["ok_at"])

    def test_timeout_is_unreachable_not_expired(self):
        def boom(*a, **k):
            raise TimeoutError("read timed out")
        with mock.patch("httpx.post", boom):
            with self.assertRaises(TimeoutError):
                self.ask()
        self.assertEqual(self.llm.health()["state"], "unreachable")

    def test_probe_swallows_failure_and_reports(self):
        with mock.patch("httpx.post", lambda *a, **k: _Resp("x", 401)):
            h = self.llm.probe()
        self.assertEqual(h["state"], "key_expired")
        with mock.patch("httpx.post", lambda *a, **k: _Resp("OK")):
            self.assertEqual(self.llm.probe()["state"], "ok")


class ConfigCarriesHealth(unittest.TestCase):
    def test_config_has_health_without_error_text(self):
        from fastapi.testclient import TestClient
        import artquest.llm as llm
        from artquest.main import app
        llm._note_health("key_expired", 401)
        try:
            body = TestClient(app).get("/api/v1/config").json()
        finally:
            llm.reset_health()
        h = body["llm"]["health"]
        self.assertEqual(h["state"], "key_expired")
        self.assertEqual(set(h), {"state", "since", "ok_at", "fail_at", "http_status"})
        self.assertNotIn("error", h)


if __name__ == "__main__":
    unittest.main()
