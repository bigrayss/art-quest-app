# -*- coding: utf-8 -*-
"""只剩简单版（2026-10-12 用户删掉了「简单版 / 完整版」两档）与注册时的年龄。

ui 只剩 simple | quiet：quiet 是研究员定的对照组，客户端改不动；旧客户端送来的 "full" 折成 simple。
年龄是首访任务库的路由输入和分析协变量。
"""
import unittest

from .env import ADMIN, TMP as _TMP  # noqa: F401  (offline backends, throwaway data dir)

from fastapi.testclient import TestClient  # noqa: E402

from artquest import study as study_mod  # noqa: E402
from artquest.main import app  # noqa: E402


class SimpleMode(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def _session(self, **extra):
        body = {"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""}}
        body.update(extra)
        r = self.c.post("/api/sessions", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["session"]

    def test_age_is_required_for_students_and_bounded(self):
        """年龄是学生账号最要紧的属性（2026-10-09 用户定）：不填不给注册；之后能改。"""
        r = self.c.post("/api/accounts/register", json={"name": "七岁", "pin": "1111", "age": 7})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["account"]["age"], 7)
        r = self.c.post("/api/accounts/register", json={"name": "没填", "pin": "1111"})
        self.assertEqual(r.status_code, 422, r.text)
        # 成年初学者也用这个 app（用户 2026-10-11）：30 岁能注册；上限只是防手滑
        self.assertEqual(self.c.post("/api/accounts/register", json={"name": "三十", "pin": "1111", "age": 30}).status_code, 201)
        self.assertEqual(self.c.post("/api/accounts/register", json={"name": "手滑", "pin": "1111", "age": 130}).status_code, 422)
        tok = self.c.post("/api/accounts/register", json={"name": "填错了", "pin": "1111", "age": 7}).json()["token"]
        r = self.c.post("/api/accounts/profile", json={"token": tok, "age": 9})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["account"]["age"], 9)
        self.assertEqual(self.c.post("/api/accounts/profile", json={"token": tok, "age": 40}).status_code, 200)
        self.assertEqual(self.c.post("/api/accounts/profile", json={"token": tok, "age": 140}).status_code, 422)

    def test_only_the_simple_version_exists_and_age_rides_along(self):
        s = self._session(condition={"ui": "simple"},
                          participant={"anon_id": "dev-s", "account_id": "", "age": 7})
        self.assertEqual(s["condition"]["ui"], "simple")
        self.assertEqual(s["participant"]["age"], 7)
        s = self._session()
        self.assertEqual(s["condition"]["ui"], "simple", "默认就是简单版")
        self.assertIsNone(s["participant"]["age"])
        s = self._session(condition={"ui": "full"})
        self.assertEqual(s["condition"]["ui"], "simple", "完整版已删：旧客户端送 full 也折成 simple")
        cfg = self.c.get("/api/config").json()
        self.assertEqual(cfg["default_condition"]["ui"], "simple")

    def test_protocols_rotate_only_the_simple_tier_by_default(self):
        from artquest.study import _forms_of
        forms = _forms_of("M4", {})
        self.assertTrue(forms)
        self.assertFalse([f for f in forms if "_J" in f], "初中题留在库里，不再分给任何人")
        self.assertTrue(all("_A" in f or "_E" in f for f in forms))

    def test_a_control_arm_cannot_be_switched_off_from_the_device(self):
        study_mod.save_study({"active": True, "study_id": "s-quiet", "order": "latin",
                              "condition": {"ui": "quiet"}})
        try:
            s = self._session(condition={"ui": "simple"}, study={"active": True, "study_id": "s-quiet"})
            self.assertEqual(s["condition"]["ui"], "quiet", "对照组是实验臂，孩子的开关改不动它")
            # 研究员自己可以把整组设成 simple
            study_mod.save_study({"condition": {"ui": "simple"}})
            s = self._session(condition={}, study={"active": True, "study_id": "s-quiet"})
            self.assertEqual(s["condition"]["ui"], "simple")
        finally:
            study_mod.save_study({"active": False, "study_id": "", "condition": {"ui": "simple"}})


if __name__ == "__main__":
    unittest.main()
