# -*- coding: utf-8 -*-
"""首访任务库（2026-10-12，docs/Task_Library_zh_CN.md v1.0.0）：25 道按年龄五段路由，每段固定五道。

守的是文档第三节「所有任务共用的实施与完成后配置」变成代码之后的样子：
空白画布单幅产出、参考图 contain 常显、提示按需且记事件、没有限时、首访不开修改轮、三题可跳过、
年龄是路由不是分数、范围外不静默分配。
"""
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from .env import TMP as _TMP  # noqa: F401

from artquest.main import app  # noqa: E402
from artquest.missions import build_library, FAMILIES  # noqa: E402
from artquest.missions_bank import BANDS, BANK, ORDER, band_of, tasks  # noqa: E402
from artquest.missions_en import translate_task  # noqa: E402
from artquest.quests import QUESTS_BY_ID, condition_snapshot  # noqa: E402
from artquest.events import HINT_SHOW, is_known  # noqa: E402
from artquest.scoring.base import DIM_KEYS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BANK_ROWS = [r for r in build_library() if r.get("bank")]


class Library(unittest.TestCase):
    def test_twenty_five_tasks_five_per_band_in_fixed_order(self):
        self.assertEqual(len(BANK_ROWS), 30)
        by_band = {}
        for r in BANK_ROWS:
            by_band.setdefault(r["band"], []).append(r["family"])
        self.assertEqual(sorted(by_band), [b["id"] for b in BANDS])
        for band, fams in by_band.items():
            self.assertEqual(fams, ORDER, band)          # 观察 / 表达 / 图形片段 / 物品改造 / 视觉设计，顺序固定
        for r in BANK_ROWS:
            self.assertRegex(r["task_id"], r"^B[1-6]_(OB|ST|FG|TR|DS)_01$")
            self.assertEqual(r["tiers"], [])             # 不进简单版 / 完整版的抽题
            self.assertFalse(r["legacy"])
            self.assertIsNone(r["time_limit_sec"])       # 没有 60 秒阶段、没有限时
            self.assertIsNone(r["phases"])
            self.assertIn(r["family"], FAMILIES)

    def test_every_task_carries_what_the_learner_sees_and_nothing_hidden(self):
        for r in BANK_ROWS:
            self.assertTrue(r["instruction"] and r["requirements"] and r["card"] and r["reflection"], r["task_id"])
            self.assertEqual([h["id"] for h in r["hints"]], ["H1", "H2"], r["task_id"])
            self.assertEqual(r["hint"], "")              # 提示不是单条 hint 字段，是按需显示的两条
            self.assertEqual(r["condition"]["revision_enabled"], True)    # 修改轮和 M 族一样都有（2026-10-12 用户定）
            self.assertEqual(r["condition"]["post_config"], "first_visit_common_v1")
            self.assertEqual(r["condition"]["reference_fit"], "contain")
            # 必要条件和题面一致：文档说「不在研究分析时补加隐藏要求」——快照里也冻着原文
            snap = condition_snapshot(QUESTS_BY_ID[r["task_id"]])
            self.assertEqual(snap["requirements"], r["requirements"])
            self.assertEqual(snap["hints"], r["hints"])
            self.assertEqual(snap["bank"], BANK)

    def test_rubric_is_primary_from_the_document_and_everything_else_exploratory(self):
        for r in BANK_ROWS:
            q = QUESTS_BY_ID[r["task_id"]]
            prim = q["rubric"]["primary_dimensions"]
            self.assertTrue(prim, r["task_id"])
            self.assertTrue(set(prim) <= set(DIM_KEYS))
            self.assertEqual(q["rubric"]["secondary_dimensions"], [])
            self.assertEqual(q["rubric"]["not_applicable_dimensions"], [])   # 全部允许上色：九维全评
            notes = {d["key"]: d for d in q["dim_notes"]}
            for d in prim:
                self.assertEqual(notes[d]["role"], "primary")

    def test_reference_images_are_real_contain_and_carry_their_native_size(self):
        """2026-10-12 用户给的 v3 包：插画版 9 张是展示拼版的原生裁切（295–443 px），6 张旧素材 1600×1200。
        不放大、不裁切，contain 显示；行上记实际尺寸；manifest 里不再是占位。"""
        from PIL import Image
        n = 0
        for r in BANK_ROWS:
            stim = r["stimulus"]
            if stim["kind"] == "none":
                self.assertIn(r["family"], ("ST", "DS"))
                continue
            n += 1
            self.assertEqual(stim["mode"], "always")
            self.assertEqual(stim["fit"], "contain")
            p = ROOT / stim["file"].lstrip("/")
            self.assertTrue(p.exists(), p)
            with Image.open(p) as im:
                self.assertEqual(list(im.size), stim["size"], r["task_id"])
                self.assertGreaterEqual(min(im.size), 290, "小于展示拼版原生尺寸 = 被缩过")
            self.assertFalse(QUESTS_BY_ID[r["task_id"]]["stimulus_placeholder"], "真图已到位，不该再标 placeholder")
            self.assertFalse(stim["svg"], "v3 包没有可编辑 SVG，不能假称有")
        self.assertEqual(n, 18)

    def test_english_travels_with_the_row(self):
        for r in BANK_ROWS:
            en = translate_task(QUESTS_BY_ID[r["task_id"]])
            self.assertNotEqual(en["instruction"], r["instruction"])
            self.assertEqual([h["id"] for h in en["hints"]], ["H1", "H2"])
            self.assertTrue(en["requirements"] and en["reflection"] and en["card"])
            self.assertIn(en["family_name"], ("Observation", "Expression", "Fragments", "Redesign", "Design"))

    def test_the_json_is_what_the_docs_say(self):
        """题库读的是 bank JSON；JSON 由两份 md 生成——25 道题面必须和学生题面文档逐字一致。"""
        doc = (ROOT / "docs" / "Student_Tasks_CN_EN.md").read_text("utf-8")
        for t in tasks():
            self.assertIn(t["zh"]["prompt"], doc, t["task_id"])
            self.assertIn(t["en"]["prompt"], doc, t["task_id"])


class Routing(unittest.TestCase):
    def test_age_routes_to_a_band_and_out_of_range_is_not_silently_assigned(self):
        self.assertEqual(band_of(6)["id"], "B1")
        self.assertEqual(band_of(10)["id"], "B2")
        self.assertEqual(band_of(11)["id"], "B3")
        self.assertEqual(band_of(14)["id"], "B4")
        self.assertEqual(band_of(16)["id"], "B5")
        self.assertEqual(band_of(17)["id"], "B6")     # 17 岁及以上：成年初学者也用这个 app
        self.assertEqual(band_of(45)["id"], "B6")
        for bad in (5, 100, None, "", "x"):
            self.assertEqual(band_of(bad), {}, bad)

    def test_config_exposes_the_bands_and_quests_expose_the_bank(self):
        from artquest import config as cfg_mod
        c = TestClient(app)
        self.assertFalse(c.get("/api/v1/config").json()["first_visit"]["enabled"])   # tests/env.py 关着它
        old = cfg_mod.FIRST_VISIT_BANK; cfg_mod.FIRST_VISIT_BANK = True
        try:
            cfg = c.get("/api/v1/config").json()["first_visit"]
        finally:
            cfg_mod.FIRST_VISIT_BANK = old
        self.assertTrue(cfg["enabled"])
        self.assertEqual([b["id"] for b in cfg["bands"]], ["B1", "B2", "B3", "B4", "B5", "B6"])
        self.assertEqual(cfg["order"], ORDER)
        qs = c.get("/api/v1/quests").json()
        bank = [q for q in qs if q.get("bank")]
        self.assertEqual(len(bank), 30)
        self.assertTrue(all(q["hints"] and q["requirements"] for q in bank))
        en = [q for q in c.get("/api/v1/quests", headers={"Accept-Language": "en"}).json() if q.get("bank")]
        self.assertEqual(en[0]["hints"][0]["id"], "H1")
        # 第六段的图沿用 M 族素材，一张是 jpg
        b6 = {q["task_id"]: q for q in bank if q["band"] == "B6"}
        self.assertEqual(len(b6), 5)
        self.assertTrue(b6["B6_OB_01"]["stimulus"]["file"].endswith(".jpg"))
        self.assertNotEqual(en[0]["instruction"], bank[0]["instruction"])


class Session(unittest.TestCase):
    def test_a_bank_session_records_routing_hints_and_the_skippable_questionnaire(self):
        c = TestClient(app)
        body = {"quest_id": "B2_FG_01", "intent": {"emotion": "", "text": ""}, "participant": {"anon_id": "t-bank"},
                "routing": {"age": 9, "age_source": "asked", "band": "B2", "first_visit": True, "bank": BANK}}
        r = c.post("/api/v1/sessions", json=body); self.assertEqual(r.status_code, 201, r.text)
        sid = r.json()["session"]["session_id"]
        meta = c.get(f"/api/v1/sessions/{sid}").json()
        self.assertEqual(meta["routing"]["band"], "B2")
        self.assertEqual(meta["routing"]["age_source"], "asked")
        snap = meta["condition_snapshot"] if "condition_snapshot" in meta else meta.get("task", {})
        self.assertEqual((snap.get("task_condition") or snap.get("condition") or {}).get("revision_enabled"), True)
        # 提示显示是词表里的事件
        self.assertTrue(is_known(HINT_SHOW))
        r = c.post(f"/api/v1/sessions/{sid}/log", json={"events": [{"type": "HINT_SHOW", "t_ms": 1200, "payload": {"hint_id": "H1", "task_id": "B2_FG_01", "n": 1}}], "strokes": []})
        self.assertEqual(r.status_code, 200, r.text)
        # 三题各可跳过：只答了喜欢程度，难度和反思跳过 → 记进 skipped，不补成 0
        r = c.post(f"/api/v1/sessions/{sid}/questionnaire",
                   json={"enjoyment": 4, "reflection": "", "instrument": "first_visit_common_v1", "skipped": ["difficulty", "reflection"], "t_ms": 5000})
        self.assertEqual(r.status_code, 200, r.text)
        q = r.json()["questionnaire"]
        self.assertEqual(q["enjoyment"], 4)
        self.assertIsNone(q.get("difficulty"))
        self.assertEqual(q["skipped"], ["difficulty", "reflection"])
        self.assertEqual(q["instrument"], "first_visit_common_v1")
