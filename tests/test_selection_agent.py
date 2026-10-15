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


# ---------------------------------------------------------------------------
# 第二步：循环、预算、执行关联（假模型：httpx.post 换成按剧本回 tool_calls）
# ---------------------------------------------------------------------------
import json  # noqa: E402
from unittest import mock  # noqa: E402


class _ToolResp:
    """OpenAI 兼容的一条回复：tool_calls 或正文。"""

    def __init__(self, calls=None, text=""):
        self.status_code = 200
        self.headers = {}
        self.calls = calls or []
        self.text_ = text
        self.text = text

    def json(self):
        msg = {"role": "assistant", "content": self.text_}
        if self.calls:
            msg["tool_calls"] = [{"id": f"tc_{i}", "type": "function",
                                  "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}}
                                 for i, (n, a) in enumerate(self.calls)]
        return {"id": "chatcmpl-tool", "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "choices": [{"finish_reason": "tool_calls" if self.calls else "stop", "message": msg}]}


class Loop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Tools.setUpClass()
        for k in ("c", "store", "who", "other", "m6", "m9", "s_m6", "s_m9", "before", "s_late", "s_other"):
            setattr(cls, k, getattr(Tools, k))

    def setUp(self):
        self.llm = agent.llm
        self.saved = (self.llm.LLM_PROVIDER, self.llm.LLM_BASE_URL, self.llm.LLM_MODEL, list(self.llm._POOL.keys))
        self.llm.LLM_PROVIDER, self.llm.LLM_BASE_URL, self.llm.LLM_MODEL = "openai", "https://fake/v1", "fake-model"
        self.llm._POOL.keys = ["sk-fake"]
        self.script, self.requests, self.records = [], [], []
        def post(url, json=None, **k):
            self.requests.append(json)
            if not self.script:
                raise TimeoutError("read timed out")
            r = self.script.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        self.p1 = mock.patch("httpx.post", post); self.p1.start()
        self.p2 = mock.patch("time.sleep", lambda *_: None); self.p2.start()

    def tearDown(self):
        self.p1.stop(); self.p2.stop()
        self.llm.LLM_PROVIDER, self.llm.LLM_BASE_URL, self.llm.LLM_MODEL, self.llm._POOL.keys = self.saved

    def _ctx(self, n_free=1):
        decision = sel.compute("map", self.who, [self.m6, self.m9], age=9)
        decision["rules_fill"] = sel.pool_for(decision)[:n_free]
        fixed = [o["task_id"] for o in decision["offered"] if QUESTS_BY_ID[o["task_id"]].get("bank")]
        return agent.AgentContext(store=self.store, decision=decision, who=self.who, before=self.before,
                                  pool=sel.pool_for(decision), n_free=n_free, fixed=fixed)

    def _run(self, ctx, **budget):
        sink = lambda rec, system=None: self.records.append(rec)
        with self.llm.recording(sink, purpose="select", stage="bank_rotation", prompt_version=agent.PROMPT_VERSION) as parent:
            try:
                out = agent.run_agent(ctx, rep={"n_tasks": 2, "tasks": []}, parent=parent, budget=budget or None)
            except agent.AgentFailed as e:
                out = e
        return out, parent

    def test_retrieve_then_fix_a_duplicate_then_submit(self):
        ctx = self._ctx(n_free=2)
        pool = ctx.pool
        self.script = [
            _ToolResp([("retrieve_history", {"family": "M6", "limit": 1})]),
            _ToolResp([("validate_offer", {"ranked": [pool[0], pool[0]], "evidence": [self.s_m6]})]),
            _ToolResp([("submit_offer", {"ranked": [pool[0], pool[1]], "evidence": [self.s_m6], "why": "最近 M6 改过、颜色在涨"})]),
        ]
        out, parent = self._run(ctx)
        self.assertNotIsInstance(out, Exception, out)
        self.assertEqual(out["ranked"], [pool[0], pool[1]])
        self.assertEqual(out["evidence"], [self.s_m6])
        a = out["agent"]
        self.assertEqual(a["stopped"], "submitted")
        self.assertEqual(a["counts"], {"rounds": 3, "tool_calls": 3, "retrieve": 1, "validate": 1, "submit": 1, "runtime_validate": 1})
        kinds = [(t["kind"], t.get("tool_name"), t.get("requested_by")) for t in a["trace"]]
        self.assertEqual(kinds, [("model", None, None), ("tool", "retrieve_history", "model"),
                                 ("model", None, None), ("tool", "validate_offer", "model"),
                                 ("model", None, None), ("tool", "validate_offer", "runtime")])
        self.assertEqual(a["trace"][3]["errors"], ["DUPLICATE_TASK", "WRONG_COUNT"])
        # 真实返回进了下一轮输入：第二次请求里有查到的 session id，第三次里有错误码
        self.assertEqual(len(self.requests), 3)
        tool_msgs = [m for m in self.requests[1]["messages"] if m["role"] == "tool"]
        self.assertIn(self.s_m6, tool_msgs[-1]["content"])
        self.assertNotIn(self.s_late, tool_msgs[-1]["content"])
        self.assertIn("DUPLICATE_TASK", [m for m in self.requests[2]["messages"] if m["role"] == "tool"][-1]["content"])
        self.assertEqual([t["type"] for t in self.requests[0]["tools"]], ["function"] * 3)
        # 记录：3 条远程（各自 operation、tags.step/role）+ 3 条工具 local（tool_name / requested_by / 关联的模型 call_id）
        remote = [r for r in self.records if r["execution_kind"] == "remote"]
        local = [r for r in self.records if r["execution_kind"] == "local"]
        self.assertEqual(len(remote), 3)
        self.assertEqual(len({r["operation_id"] for r in remote}), 3)
        self.assertEqual([r["round"] for r in remote], [1, 2, 3])
        self.assertTrue(all(r["role"] == "model_round" and r["purpose"] == "select" for r in remote))
        self.assertEqual([(r["tool_name"], r["requested_by"]) for r in local],
                         [("retrieve_history", "model"), ("validate_offer", "model"), ("validate_offer", "runtime")])
        self.assertEqual([r["model_call_id"] for r in local], [r["call_id"] for r in remote])
        self.assertEqual(local[0]["backend"], "runtime")
        self.assertEqual(local[0]["output"]["sessions"][0]["session_id"], self.s_m6)
        self.assertEqual(len({r["group_id"] for r in self.records}), 1)
        self.assertEqual(parent.count_remote(), 3)

    def test_information_enough_means_submit_straight_away(self):
        ctx = self._ctx()
        self.script = [_ToolResp([("submit_offer", {"ranked": [ctx.pool[2]], "why": "够了"})])]
        out, _ = self._run(ctx)
        self.assertEqual(out["ranked"], [ctx.pool[2]])
        self.assertEqual(out["agent"]["counts"]["tool_calls"], 1)
        self.assertEqual(out["agent"]["counts"]["retrieve"], 0)
        self.assertEqual([t["kind"] for t in out["agent"]["trace"]], ["model", "tool"])
        self.assertEqual(out["agent"]["trace"][1]["requested_by"], "runtime", "没主动校验也要过最终那道")

    def test_json_in_plain_text_counts_as_a_submission(self):
        ctx = self._ctx()
        self.script = [_ToolResp(text='{"ranked": ["%s"], "why": "直接给"}' % ctx.pool[1])]
        out, _ = self._run(ctx)
        self.assertEqual(out["ranked"], [ctx.pool[1]])

    def test_no_tool_and_no_json_gets_one_reminder_then_fails(self):
        ctx = self._ctx()
        self.script = [_ToolResp(text="我觉得给他画画吧"), _ToolResp(text="随便哪道都行")]
        out, _ = self._run(ctx)
        self.assertIsInstance(out, agent.AgentFailed)
        self.assertEqual(out.reason, "bad_output")
        self.assertIn("submit_offer", self.requests[1]["messages"][-1]["content"])

    def test_invalid_submissions_exhaust_the_model_budget_and_fall_back(self):
        ctx = self._ctx()
        bad = _ToolResp([("submit_offer", {"ranked": ["nope"], "why": ""})])
        self.script = [bad, bad, bad, bad, bad]
        out, parent = self._run(ctx)
        self.assertIsInstance(out, agent.AgentFailed)
        self.assertEqual(out.reason, "budget_exhausted")
        self.assertEqual(len(self.requests), 4)                      # 最多 4 次模型请求
        runtime = [r for r in self.records if r["execution_kind"] == "local" and r["requested_by"] == "runtime"]
        self.assertEqual(len(runtime), 4)
        self.assertTrue(all(r["outcome"] == "error" for r in runtime))

    def test_retrieve_budget_is_enforced_by_the_runtime(self):
        ctx = self._ctx()
        r = _ToolResp([("retrieve_history", {"limit": 2})])
        self.script = [r, r, r, _ToolResp([("submit_offer", {"ranked": [ctx.pool[0]], "why": "x"})])]
        out, _ = self._run(ctx)
        self.assertEqual(out["ranked"], [ctx.pool[0]])
        self.assertEqual(out["agent"]["counts"]["retrieve"], 2)
        third = [m for m in self.requests[3]["messages"] if m["role"] == "tool"][-1]["content"]
        self.assertIn("BUDGET_EXCEEDED", third)

    def test_http_timeout_and_decision_deadline(self):
        ctx = self._ctx()
        self.script = []                                               # 假模型直接超时
        out, _ = self._run(ctx)
        self.assertIsInstance(out, agent.AgentFailed)
        self.assertEqual(out.reason, "timeout")
        remote = [r for r in self.records if r["execution_kind"] == "remote"]
        self.assertEqual([r["outcome"] for r in remote], ["exception"])
        # 总期限：时钟假装一下子过了
        ticks = iter([0.0, 1000.0, 1000.0, 1000.0])
        self.script = [_ToolResp([("retrieve_history", {})]), _ToolResp([("submit_offer", {"ranked": [ctx.pool[0]], "why": ""})])]
        sink = lambda rec, system=None: None
        with self.llm.recording(sink, purpose="select") as parent:
            with self.assertRaises(agent.AgentFailed) as cm:
                agent.run_agent(self._ctx(), rep=None, parent=parent, budget={"seconds": 10.0}, clock=lambda: next(ticks))
        self.assertEqual(cm.exception.reason, "timeout")

    def test_evidence_must_be_real_history(self):
        ctx = self._ctx()
        self.script = [_ToolResp([("submit_offer", {"ranked": [ctx.pool[0]], "evidence": [self.s_other], "why": ""})]),
                       _ToolResp([("submit_offer", {"ranked": [ctx.pool[0]], "evidence": [self.s_m9], "why": ""})])]
        out, _ = self._run(ctx)
        self.assertEqual(out["evidence"], [self.s_m9])
        self.assertEqual(out["agent"]["trace"][1]["errors"], ["INVALID_EVIDENCE_REF"])
