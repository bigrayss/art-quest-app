# -*- coding: utf-8 -*-
"""任务空间（Phase 0）：来源能解释目标、蓝图能约束起草、属性能描述真实任务、材料能实现条件。

守的是关系，不是分数：每道 v2 题都是完整候选；引用的片段都存在；检查器能抓住已知的反例；
而且这一层**只读**题库——TASK_VERSION 和 build_library() 的行数、id 不因它改变。
"""
import unittest

from artquest.missions import TASK_VERSION, build_library
from artquest.scoring.base import DIM_KEYS
from artquest.taskspace import initialize
from artquest.taskspace.blueprints import BLUEPRINTS, CAPABILITIES, OPERATIONS
from artquest.taskspace.candidates import build_candidates, required_outputs
from artquest.taskspace.checks import mutations, rule_checks, semantic_checks, FAIL, CONTRADICTS, BLOCKED
from artquest.taskspace.materials import MATERIALS, check_material, crop_box, questions
from artquest.taskspace.sources import EXCERPTS, SOURCES, PENDING, RELATIONS


class Sources(unittest.TestCase):
    def test_every_excerpt_points_at_a_registered_source_and_keeps_both_page_numbers(self):
        for e in EXCERPTS.values():
            self.assertIn(e["source"], SOURCES, e["id"])
            if e["source"] == "kb2022":
                # 正文页与 PDF 页分开记，偏移是核对过的 7
                self.assertEqual(e["page_pdf"], e["page_body"] + 7, e["id"])
                self.assertTrue(e["text"], e["id"])

    def test_a_pending_excerpt_never_counts_as_support(self):
        """没拿到原文的片段留空、状态「待录入」；检查器把它记成未决，不记成找到支持。
        （2026-10-11 之后库里引用的片段都已核对，所以这里自己造一条来守规则。）"""
        from artquest.taskspace import sources as src
        src.EXCERPTS["test:pending"] = dict(id="test:pending", source="kb2022", page_body=1, page_pdf=8, band="", heading="x",
                                            text="", requirement="x", scope="", verified=PENDING)
        try:
            c = next(c for c in build_candidates() if c["task_id"] == "M9_A1")
            c["source_relations"] = list(c["source_relations"]) + [dict(requirement="x", relation="原文明确规定", excerpt="test:pending", purpose="")]
            rules = {i["rule"]: i["status"] for i in rule_checks(c)}
            self.assertEqual(rules.get("R1 片段已录入原文"), "undetermined")
            sem = [i for i in semantic_checks(c) if i["basis"].startswith("test:pending")]
            self.assertEqual(sem[0]["status"], "依据不足")
        finally:
            del src.EXCERPTS["test:pending"]
        for e in EXCERPTS.values():
            if e["verified"] == PENDING:
                self.assertEqual(e["text"], "", e["id"])


class Blueprints(unittest.TestCase):
    def test_every_family_has_a_blueprint_answering_six_questions(self):
        fams = {t["family"] for t in build_library()}
        for fam in fams:
            bp = BLUEPRINTS[f"BP_{fam}"]
            for k in ("band_proposed", "goal", "operation", "inputs", "outputs", "invariants"):
                self.assertTrue(bp[k], f"{fam}.{k}")
            self.assertIn(bp["operation"], OPERATIONS)

    def test_project_added_conditions_always_state_their_purpose(self):
        for bid, bp in BLUEPRINTS.items():
            for r in bp["source_relations"]:
                self.assertIn(r["relation"], RELATIONS)
                if r["relation"] == "项目新增条件":
                    self.assertTrue(r["purpose"], f"{bid}: {r['requirement']}")
                else:
                    self.assertIn(r["excerpt"], EXCERPTS, f"{bid}: {r['requirement']}")


class Candidates(unittest.TestCase):
    def test_every_v2_task_is_a_complete_candidate(self):
        lib = {t["task_id"]: t for t in build_library() if not t.get("legacy")}
        cands = {c["task_id"]: c for c in build_candidates()}
        self.assertEqual(set(lib), set(cands))
        for tid, c in cands.items():
            for k in ("copy", "fixed", "free", "source_relations", "dims", "materials", "outputs", "variation"):
                if k == "dims" and c["family"] == "M0":
                    continue   # M0 的 rubric 全部 exploratory：没有 primary/secondary 是合法取值
                self.assertTrue(c[k] is not None and c[k] != [], f"{tid}.{k}")
            self.assertEqual(c["copy"]["instruction"], lib[tid]["instruction"])
            self.assertEqual(c["copy"]["version"], lib[tid]["version"])   # M 族 = TASK_VERSION；首访库有自己的 1.0.0
            # 无参考图是明确配置，不是漏字段
            if c["materials"]["kind"] == "none":
                self.assertIn("note", c["materials"])
            else:
                self.assertIsNotNone(c["materials"]["spec"], tid)

    def test_dimension_links_carry_a_reason_and_a_bypass_verdict(self):
        for c in build_candidates():
            for d in c["dims"]:
                self.assertIn(d["dim"], DIM_KEYS)
                self.assertTrue(d["why"])
                self.assertIn(d["bypass"], (True, False), f"{c['task_id']}:{d['dim']}")

    def test_required_outputs_reads_only_output_words(self):
        self.assertEqual(required_outputs("画出两种图书角布局。"), 2)
        self.assertEqual(required_outputs("画里要有这两点：人比虫子小。"), 1)   # 规则，不是产出
        self.assertEqual(required_outputs("至少能救两个人。"), 1)

    def test_the_library_is_untouched_by_initialisation(self):
        before = [(t["task_id"], t["instruction"]) for t in build_library()]
        initialize()
        self.assertEqual(before, [(t["task_id"], t["instruction"]) for t in build_library()])
        self.assertEqual(TASK_VERSION, "2.7")


class Checks(unittest.TestCase):
    def test_the_live_library_has_no_blocked_candidate(self):
        ts = initialize()
        self.assertEqual(ts["summary"]["status"]["blocked"], 0, ts["summary"]["failing_rules"])
        # 2026-10-11：M3 的范式来源改记 Urban (2005) p.273 后 clear；M4_J4 把「看得出是茶壶变的」写进题面后 R15 不再响
        self.assertTrue(all(c["status"] == "clear" for c in ts["candidates"] if c["family"] == "M3"))
        j4 = next(c for c in ts["candidates"] if c["task_id"] == "M4_J4")
        self.assertFalse([i for i in j4["issues"] if i["rule"].startswith("R15")])
        # 草案走同一套检查，没进库：D2 的参考图还没做，就该是 blocked，不放宽
        self.assertTrue(all(c["status"] == "blocked" for c in ts["drafts"]["candidates"] if c["family"] == "D2"))
        self.assertTrue(all(c["status"] == "clear" for c in ts["drafts"]["candidates"] if c["family"] == "D1"))

    def test_instance_level_demotion_keeps_the_record_and_the_exceptions(self):
        rows = {t["task_id"]: t for t in build_library()}
        m9 = rows["M9_A1"]
        self.assertEqual(m9["rubric"]["secondary_dimensions"], [])
        self.assertEqual(m9["rubric_overrides"]["color_richness"]["from"], "secondary")
        self.assertEqual(m9["rubric_overrides"]["color_richness"]["to"], "exploratory")
        # 家族契约本身没动；primary 一个不少
        from artquest.missions import FAMILIES
        self.assertEqual(FAMILIES["M9"]["rubric"]["secondary_dimensions"], ["transformation", "color_richness", "line_combination"])
        self.assertEqual(m9["rubric"]["primary_dimensions"], FAMILIES["M9"]["rubric"]["primary_dimensions"])
        # 例外：M8 尺度规则题保留「变形」
        self.assertIn("deformation", rows["M8_E3"]["rubric"]["secondary_dimensions"])
        self.assertNotIn("deformation", rows["M8_A1"]["rubric"]["secondary_dimensions"])

    def test_counterexamples_are_caught(self):
        """检查器连明确冲突都抓不到，就不该信它更模糊的判断。"""
        base = next(c for c in build_candidates() if c["task_id"] == "M5_A1")
        for mut in mutations(base):
            issues = rule_checks(mut["candidate"]) + semantic_checks(mut["candidate"])
            hit = {i["rule"] for i in issues if i["status"] in (FAIL, CONTRADICTS, BLOCKED)}
            for rule in mut["expect"]:
                self.assertIn(rule, hit, f"{mut['name']} 没被抓到；抓到的是 {hit}")

    def test_rule_and_model_judgements_are_kept_apart(self):
        c = next(c for c in build_candidates() if c["task_id"] == "M9_A1")
        for i in rule_checks(c):
            self.assertEqual(i["judge"], "rule")
        fake = lambda cand: dict(operation="observe_represent", outputs=1, uses_reference=False)
        s = semantic_checks(c, judge=fake)
        contradiction = [i for i in s if i["rule"].startswith("S1")]
        self.assertTrue(contradiction and contradiction[0]["judge"] == "model")

    def test_multi_output_tasks_block_on_missing_capability(self):
        self.assertFalse(CAPABILITIES["multi_sketch_output"])


class Materials(unittest.TestCase):
    def test_every_stimulus_in_the_library_has_a_spec_and_a_file(self):
        for t in build_library():
            if t.get("legacy"):
                continue
            stim = t.get("stimulus") or {}
            if stim.get("kind") in ("reference", "fragments"):
                self.assertIn(stim["stimulus_id"], MATERIALS, t["task_id"])

    def test_visual_questions_are_ordered_by_dependency_and_block_on_failed_premises(self):
        qs = questions(MATERIALS["m2_scene_a"])
        ids = [q["id"] for q in qs]
        for q in qs:
            for r in q["requires"]:
                self.assertLess(ids.index(r), ids.index(q["id"]))
        # 杯子不存在 → 不再肯定「杯子的遮挡方式正确」
        r = check_material("m2_scene_a", judge=lambda path, q: "不符合" if q.startswith("图中是否存在") else "符合")
        statuses = {i["id"]: i["status"] for i in r["items"]}
        self.assertEqual(statuses["obj0"], "不符合")
        self.assertEqual(statuses["rec0"], "阻塞")
        self.assertEqual(r["status"], "不符合")   # 不用平均分盖掉失败

    def test_without_a_vision_judge_nothing_is_claimed(self):
        r = check_material("m1_scene_a")
        self.assertIn(r["status"], ("无法判断", "不符合"))
        self.assertTrue(any(i["status"] == "无法判断" for i in r["items"]))

    def test_display_frame_crop_is_centred(self):
        self.assertEqual(crop_box(2048, 1408, 2.0), (0, 192, 2048, 1216))

    def test_measurable_conditions_are_actually_measured(self):
        r = check_material("m4_umbrella")
        ids = {i["id"] for i in r["items"]}
        self.assertTrue({"size", "white_bg", "fill", "crop_thumb_desktop"} <= ids)
