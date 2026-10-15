"""agent 臂的两个工具（第三阶段第一步）：不调模型也能证明它们真的在读记录、真的在查。

守四件事：
1. retrieve_history 读的是允许范围内的真实记录：身份注入（别的孩子看不见）、截止时间 before（之后的看不见）、
   按家族 / 维度 / 反馈类型筛、最多 2 条、文本截断、来源编号齐全。
2. 不存在的数据标 missing；没有 ASSIST_SHOW 事件就不说孩子看过那句陪伴。
3. validate_offer 只做确定性校验，错误码具体到位置：NOT_IN_POOL / DUPLICATE_TASK / WRONG_COUNT / FIXED_SLOT_TASK /
   UNKNOWN_TASK / INVALID_EVIDENCE_REF / BAD_ARGUMENT。
4. 工具说明里的参数边界和实现一致。

Run:  python3 -m unittest -v tests.test_selection_agent
"""
import base64
import io
import unittest
import uuid

from .env import TMP as _TMP  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest import selection as sel  # noqa: E402
from artquest import selection_agent as agent  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.quests import QUESTS_BY_ID  # noqa: E402
from artquest.storage import SessionStore, now_iso  # noqa: E402


def _png(seed=0):
    img = Image.new("RGB", (320, 220), "white")
    ImageDraw.Draw(img).ellipse((40 + seed, 40, 220, 180), fill=(150, 190, 235), outline="black", width=4)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _stroke(i):
    return {"seq": i, "stroke_id": f"s{i:05d}", "phase": "before", "tool": "pen", "color": "#000000", "size": 4,
            "opacity": 1.0, "erase": False, "pointer_type": "pen", "t0_ms": 100 * i,
            "points": [[10 + i, 10, 0, None, None, None], [40 + i, 40, 30, None, None, None]]}


class Tools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)
        cls.store = SessionStore()
        cls.who = {"anon_id": "anon-agent-" + uuid.uuid4().hex[:6]}
        cls.other = {"anon_id": "anon-agent-other-" + uuid.uuid4().hex[:6]}
        cls.m6 = sel.tier_forms("M6")[0]["id"]          # 主考 color_*
        cls.m9 = sel.tier_forms("M9")[0]["id"]          # 主考 imagination / picture_organization
        # 这个孩子：一张 M6（有陪伴 + ASSIST_SHOW、反馈、修改后终评），一张 M9（没陪伴、不修改），
        # 然后记下截止时间，再画一张 M6（截止之后，不该被看见）
        cls.s_m6 = cls._draw(cls.who, cls.m6, assist=True, revise=True)
        cls.s_m9 = cls._draw(cls.who, cls.m9, assist=False, revise=False)
        cls.before = now_iso()
        cls.s_late = cls._draw(cls.who, cls.m6, assist=False, revise=False)
        cls.s_other = cls._draw(cls.other, cls.m6, assist=False, revise=False)

    @classmethod
    def _draw(cls, who, task_id, *, assist, revise):
        c = cls.c
        sid = c.post("/api/sessions", json={"quest_id": task_id, "intent": {"emotion": "", "text": "一只猫"}, "participant": who}).json()["session_id"]
        c.post(f"/api/sessions/{sid}/log", json={"events": [], "strokes": [_stroke(1)]})
        if assist:
            r = c.post(f"/api/sessions/{sid}/assist", json={"image": _png(), "nth": 1, "click_id": "clk_shown", "n_strokes": 1}).json()
            c.post(f"/api/sessions/{sid}/log", json={"events": [{"seq": 1, "t_ms": 500, "type": "ASSIST_SHOW",
                   "payload": {"click_id": "clk_shown", "call_id": r["call_id"], "cached": False}}], "strokes": []})
            c.post(f"/api/sessions/{sid}/assist", json={"image": _png(1), "nth": 2, "click_id": "clk_unshown", "n_strokes": 1})
        c.post(f"/api/sessions/{sid}/submit", json={"image": _png(), "elapsed_ms": 1000, "phase": "before", "strokes": [_stroke(2)]})
        if revise:
            c.post(f"/api/sessions/{sid}/submit", json={"image": _png(2), "elapsed_ms": 3000, "phase": "after", "pending": 0})
        else:
            c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 2000})
        return sid

    def _ctx(self, pool=None, n_free=1, fixed=()):
        decision = sel.compute("map", self.who, [self.m6, self.m9], age=9)
        return agent.AgentContext(store=self.store, decision=decision, who=self.who, before=self.before,
                                  pool=pool if pool is not None else sel.pool_for(decision), n_free=n_free, fixed=list(fixed))

    def test_history_is_this_child_s_only_and_stops_at_before(self):
        ctx = self._ctx()
        r = agent.retrieve_history(ctx)
        self.assertTrue(r["ok"])
        ids = [s["session_id"] for s in r["sessions"]]
        self.assertEqual(ids, [self.s_m9, self.s_m6], "最近的在前；截止之后的那张和别的孩子的都看不见")
        self.assertEqual(r["n_matched"], 2)
        self.assertEqual(r["source"]["before"], self.before)
        self.assertEqual(ctx.evidence_seen, {self.s_m6, self.s_m9})
        # 别的孩子的上下文里只有他自己的
        other = agent.AgentContext(store=self.store, decision=ctx.decision, who=self.other, before=now_iso(), pool=[], n_free=0, fixed=[])
        self.assertEqual([s["session_id"] for s in agent.retrieve_history(other)["sessions"]], [self.s_other])

    def test_filters_limits_and_what_each_row_carries(self):
        ctx = self._ctx()
        r = agent.retrieve_history(ctx, family="M6")
        self.assertEqual([s["session_id"] for s in r["sessions"]], [self.s_m6])
        row = r["sessions"][0]
        self.assertEqual((row["task_id"], row["family"], row["revised"], row["status"]), (self.m6, "M6", True, "done"))
        self.assertEqual(row["task_version"], QUESTS_BY_ID[self.m6]["version"])
        self.assertEqual(sorted(row["before_scores"]), sorted(k for k in row["before_scores"]))
        self.assertTrue(row["before_scores"] and row["after_scores"], "初评和终评都有")
        self.assertEqual(row["scores_backend"], "heuristic")
        kinds = [f["feedback_type"] for f in row["feedback"]]
        self.assertEqual(kinds, ["formative", "comparison"])
        self.assertTrue(all(f["feedback_id"] and f["call_id"] for f in row["feedback"]), "每句反馈带来源编号")
        self.assertEqual(row["missing"], [])
        # 陪伴：有 ASSIST_SHOW 的那句 shown=True，没有的 shown=None（不说孩子看过）
        by = {a["click_id"]: a for a in row["assist"]}
        self.assertEqual(by["clk_shown"]["shown"], True)
        self.assertIsNone(by["clk_unshown"]["shown"])
        self.assertTrue(all(a["call_id"] for a in row["assist"]))
        # 维度筛：按任务主考维度
        dim = QUESTS_BY_ID[self.m9]["rubric"]["primary_dimensions"][0]
        r = agent.retrieve_history(ctx, dimension=dim)
        self.assertEqual([s["session_id"] for s in r["sessions"]], [self.s_m9])
        self.assertEqual(list(r["sessions"][0]["before_scores"]), [dim], "只返回问的那一维")
        # 反馈类型筛：comparison 只有修改过的那张有
        r = agent.retrieve_history(ctx, feedback_type="comparison")
        self.assertEqual([s["session_id"] for s in r["sessions"]], [self.s_m6])
        # 上限：limit 最多 2，再大也截
        r = agent.retrieve_history(ctx, limit=50)
        self.assertEqual(r["query"]["limit"], 2)
        r = agent.retrieve_history(ctx, limit=1)
        self.assertEqual((len(r["sessions"]), r["n_matched"], r["truncated"]), (1, 2, True))

    def test_missing_data_is_marked_not_invented(self):
        ctx = self._ctx()
        row = agent.retrieve_history(ctx, family="M9")["sessions"][0]
        self.assertEqual(row["revised"], False)
        self.assertEqual(row["assist"], [])
        self.assertIn("assist", row["missing"])
        self.assertEqual([f["feedback_type"] for f in row["feedback"]], ["formative"])    # 没改就没有 comparison
        self.assertTrue(row["after_scores"], "不修改时 after 是 before 的副本，分数照样在")

    def test_bad_arguments_are_errors_not_guesses(self):
        ctx = self._ctx()
        r = agent.retrieve_history(ctx, dimension="beauty")
        self.assertFalse(r["ok"])
        self.assertEqual(r["errors"][0]["code"], "BAD_ARGUMENT")
        r = agent.retrieve_history(ctx, feedback_type="praise")
        self.assertEqual(r["errors"][0]["code"], "BAD_ARGUMENT")

    def test_validate_offer_error_codes_point_at_positions(self):
        decision = sel.compute("map", self.who, [self.m6, self.m9], age=9)
        pool = sel.pool_for(decision)
        fixed = [o["task_id"] for o in decision["offered"] if QUESTS_BY_ID[o["task_id"]].get("bank")]
        ctx = agent.AgentContext(store=self.store, decision=decision, who=self.who, before=self.before, pool=pool, n_free=2, fixed=fixed)
        ok = agent.validate_offer(ctx, [pool[0], pool[1]])
        self.assertEqual(ok, {"ok": True, "errors": [], "n_free": 2})
        r = agent.validate_offer(ctx, [pool[0], pool[0]])
        self.assertEqual([(e["code"], e["position"]) for e in r["errors"]], [("DUPLICATE_TASK", 1), ("WRONG_COUNT", None)])
        r = agent.validate_offer(ctx, [pool[0]])
        self.assertEqual([e["code"] for e in r["errors"]], ["WRONG_COUNT"])
        r = agent.validate_offer(ctx, [pool[0], "nope"])
        self.assertEqual([(e["code"], e["position"]) for e in r["errors"]], [("UNKNOWN_TASK", 1), ("WRONG_COUNT", None)])
        r = agent.validate_offer(ctx, [pool[0], fixed[0]])
        self.assertEqual(r["errors"][0]["code"], "FIXED_SLOT_TASK")
        r = agent.validate_offer(ctx, [pool[0], self.m6])                 # 做过的不在池子里
        self.assertEqual(r["errors"][0]["code"], "NOT_IN_POOL")
        legacy = next(q["id"] for q in QUESTS_BY_ID.values() if q.get("legacy"))
        ctx2 = agent.AgentContext(store=self.store, decision=decision, who=self.who, before=self.before, pool=pool + [legacy], n_free=2, fixed=fixed)
        r = agent.validate_offer(ctx2, [pool[0], legacy])
        self.assertEqual(r["errors"][0]["code"], "NOT_ON_MAP")
        # 引用：只能指向允许历史里的 session
        r = agent.validate_offer(ctx, [pool[0], pool[1]], evidence=[self.s_m6, self.s_late, self.s_other, "zzz"])
        self.assertEqual([(e["code"], e["position"]) for e in r["errors"]],
                         [("INVALID_EVIDENCE_REF", 1), ("INVALID_EVIDENCE_REF", 2), ("INVALID_EVIDENCE_REF", 3)])
        r = agent.validate_offer(ctx, "not a list")
        self.assertEqual(r["errors"][0]["code"], "BAD_ARGUMENT")
        r = agent.validate_offer(ctx, [pool[0], pool[1]], evidence="x")
        self.assertEqual(r["errors"][0]["code"], "BAD_ARGUMENT")

    def test_tool_specs_match_the_implementation(self):
        names = [t["name"] for t in agent.TOOLS]
        self.assertEqual(names, ["retrieve_history", "validate_offer", "submit_offer"])
        rh = agent.TOOLS[0]["parameters"]["properties"]
        self.assertEqual(rh["limit"]["maximum"], agent.MAX_SESSIONS_PER_RETRIEVE)
        self.assertEqual(rh["dimension"]["enum"], list(agent.DIM_KEYS))
        self.assertEqual(set(agent.ERRORS), {"BAD_ARGUMENT", "UNKNOWN_TASK", "NOT_IN_POOL", "NOT_ON_MAP", "FIXED_SLOT_TASK",
                                             "DUPLICATE_TASK", "WRONG_COUNT", "INVALID_EVIDENCE_REF"})


if __name__ == "__main__":
    unittest.main()
