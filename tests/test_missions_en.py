"""任务库的英文版：从 missions.py 的行**推**出来，不是另一份题库。

中文题目是测量工具，一个字不能动，所以英文只能是翻译——每一行的要求、限制、
拼接句式都要和中文一一对应；而且 translate 不能碰原行。
"""
import copy
import re
import unittest

from artquest.missions_en import FAMILY_NAMES_EN, translate_family, translate_task
from artquest.quests import QUESTS, families

CJK = re.compile(r"[一-鿿「」，。：；！？（）]")


class EveryTaskHasAnEnglishTwin(unittest.TestCase):
    def test_every_row_translates_without_a_single_chinese_character(self):
        self.assertGreater(len(QUESTS), 50)
        for task in QUESTS:
            before = copy.deepcopy(task)
            en = translate_task(task)
            with self.subTest(task=task["task_id"]):
                for key in ("title", "instruction", "prompt", "hint", "family_name", "type"):
                    self.assertTrue(en[key], f"{key} 为空")
                    self.assertIsNone(CJK.search(en[key]), f"{key} 里还有中文：{en[key]!r}")
                self.assertEqual(en["prompt"], en["instruction"])
                self.assertEqual(en["lang"], "en")
                # 身份和研究元数据原样：它们是后面每张表的外键
                for key in ("task_id", "id", "form_id", "condition", "stimulus", "rubric", "family"):
                    self.assertEqual(en[key], task[key])
                if task.get("phases"):
                    for p_en, p_zh in zip(en["phases"], task["phases"]):
                        self.assertIsNone(CJK.search(p_en["label"]))
                        self.assertEqual({k: v for k, v in p_en.items() if k != "label"},
                                         {k: v for k, v in p_zh.items() if k != "label"})
                self.assertEqual(task, before, "translate 改了原行")

    def test_the_english_keeps_the_same_moving_parts_as_the_chinese(self):
        by_family = {}
        for t in QUESTS:
            by_family.setdefault(t["family"], []).append(t)
        # M3：末尾那张叙事卡
        for t in by_family["M3"]:
            en = translate_task(t)
            self.assertIn("Also, in this picture:", en["instruction"])
            self.assertTrue(en["instruction"].rstrip().endswith("."))
        # M8：规则一条不少
        for t in by_family["M8"]:
            en = translate_task(t)
            n = len(t["condition"]["rule_refs"])
            self.assertEqual(en["instruction"].count("\n· "), n)
        # M7：第一步的秒数
        for t in by_family["M7"]:
            en = translate_task(t)
            self.assertIn(f"({t['phases'][0]['seconds']} seconds)", en["instruction"])
            self.assertIn("Step 2", en["instruction"])
        # M5：两个概念都点了名；M4：三个格子都填了
        for t in by_family["M5"]:
            en = translate_task(t)
            self.assertIn("This time, fuse:", en["instruction"])
        for t in by_family["M4"]:
            en = translate_task(t)
            self.assertNotIn("{", en["instruction"])
        for t in by_family["M6"]:
            self.assertNotIn("{", translate_task(t)["instruction"])

    def test_families_get_english_names_and_nothing_else_changes(self):
        rows = families()
        self.assertEqual(set(FAMILY_NAMES_EN), {r["id"] for r in rows})
        for r in rows:
            en = translate_family(r)
            self.assertEqual(en["name"], FAMILY_NAMES_EN[r["id"]])
            self.assertIsNone(CJK.search(en["name"]))
            self.assertEqual({k: v for k, v in en.items() if k != "name"},
                             {k: v for k, v in r.items() if k != "name"})

    def test_a_custom_task_from_an_unknown_family_passes_through(self):
        row = {"task_id": "X1", "id": "X1", "family": "X", "form_id": "1", "title": "自定义",
               "instruction": "老师写的", "prompt": "老师写的", "hint": "", "condition": {}, "stimulus": {},
               "rubric": {}, "phases": None}
        en = translate_task(row)
        self.assertEqual(en["title"], "自定义")
        self.assertEqual(en["lang"], "en")


if __name__ == "__main__":
    unittest.main()
