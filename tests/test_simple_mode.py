# -*- coding: utf-8 -*-
"""简单版（ui: simple）与注册时的年龄。

简单版是孩子设备上的开关，只在研究员定的 ui 是 full 时起作用；对照组（quiet）是实验臂，
开关改不动它。年龄只用来推荐版本和做协变量，可不填。
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

    def test_age_is_optional_and_bounded(self):
        r = self.c.post("/api/accounts/register", json={"name": "七岁", "pin": "1111", "age": 7})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["account"]["age"], 7)
        r = self.c.post("/api/accounts/register", json={"name": "没填", "pin": "1111"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertIsNone(r.json()["account"]["age"])
        self.assertEqual(self.c.post("/api/accounts/register", json={"name": "三十", "pin": "1111", "age": 30}).status_code, 422)

    def test_the_switch_is_frozen_into_the_session_and_age_rides_along(self):
        s = self._session(condition={"ui": "simple"},
                          participant={"anon_id": "dev-s", "account_id": "", "age": 7})
        self.assertEqual(s["condition"]["ui"], "simple")
        self.assertEqual(s["participant"]["age"], 7)
        s = self._session()
        self.assertEqual(s["condition"]["ui"], "full")
        self.assertIsNone(s["participant"]["age"])

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
            study_mod.save_study({"active": False, "study_id": "", "condition": {"ui": "full"}})


if __name__ == "__main__":
    unittest.main()
