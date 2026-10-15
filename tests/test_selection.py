"""选题的服务端影子（agent 级数据计划 PR 3，2026-10-14）。

守五件事：
1. 规则复刻：首访五道 + UNLOCK_ORDER 轮转、五个待办位；协议序列；成长面板推荐；老地图家族池；年龄门；范围外回老地图。
2. /task-options：按服务端的完成记录算，冻进一张 prepared 票；同样的输入 → 同一个 decision_id（幂等）、每次展示一个 offer_id；
   客户端摆的和服务端算的比对结果记在 offer 上；历史变了旧决策进 superseded。
3. 建 session 时核对并拷贝：attached / in_offered / 票记 consumed_by；换了身份 identity_changed；重复消费 already_consumed；
   没网标 client_offline。孩子看到的题是客户端定的，服务端一个字不改。
4. prepared 票不进列表、不进历史、不进作品导出；reap 收走已消费的和放了 30 天的。
5. decisions.csv 一条 session 一行；没消费的决策另出一张表。

Run:  python3 -m unittest -v tests.test_selection
"""
import base64
import csv
import io
import tempfile
import unittest
from pathlib import Path

from .env import TMP as _TMP  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest import selection as sel  # noqa: E402
from artquest.history import iter_sessions  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.missions_bank import ORDER  # noqa: E402
from artquest.quests import QUESTS_BY_ID  # noqa: E402
from artquest.storage import SessionStore, sid_of  # noqa: E402


def _png():
    img = Image.new("RGB", (320, 220), "white")
    ImageDraw.Draw(img).ellipse((40, 40, 220, 180), fill=(150, 190, 235), outline="black", width=4)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _stroke(i):
    return {"seq": i, "stroke_id": f"s{i:05d}", "phase": "before", "tool": "pen", "color": "#000000", "size": 4,
            "opacity": 1.0, "erase": False, "pointer_type": "pen", "t0_ms": 100 * i,
            "points": [[10 + i, 10, 0, None, None, None], [40 + i, 40, 30, None, None, None]]}


class Rules(unittest.TestCase):
    WHO = {"anon_id": "anon-rules"}

    def test_first_visit_starts_with_the_band_s_five_then_unlocks_one_m_family_per_finished_drawing(self):
        d = sel.compute("map", self.WHO, [], age=9, age_source="asked")
        self.assertEqual((d["rule"], d["routing"]["band"], d["gate"]), ("bank_rotation", "B2", ""))
        offered = [o["task_id"] for o in d["offered"]]
        self.assertEqual([QUESTS_BY_ID[t]["family"] for t in offered], ORDER)        # 观察/表达/图形片段/物品改造/视觉设计
        self.assertTrue(d["locked_more"])
        self.assertTrue(all(c["bank"] or c["family"].startswith("M") for c in d["candidates"]))
        # 画完第一道：它进已完成，待办位补进来的是 M9 的第一道（UNLOCK_ORDER 第一个），不是本段的第六道
        d2 = sel.compute("map", self.WHO, [offered[0]], age=9)
        offered2 = [o["task_id"] for o in d2["offered"]]
        self.assertEqual(offered2[:4], offered[1:])
        self.assertEqual(QUESTS_BY_ID[offered2[4]]["family"], "M9")
        self.assertEqual(offered2[4], sel.tier_forms("M9")[0]["id"])
        self.assertEqual(d2["finished"], [offered[0]])
        self.assertEqual(d2["history"], {"done_task_ids": [offered[0]], "n_done": 1, "source": "server"})
        # 再画完五道 → 第二轮前每家一道（M9 M6 M3 M4 M5 M1 …）
        done = offered + [offered2[4]]
        d3 = sel.compute("map", self.WHO, done, age=9)
        fams = [o["family"] for o in d3["offered"]]
        self.assertEqual(fams, ["M6", "M3", "M4", "M5", "M1"])

    def test_no_age_is_a_gate_and_out_of_range_falls_back_to_the_family_map(self):
        d = sel.compute("map", self.WHO, [], age=None)
        self.assertEqual((d["rule"], d["gate"], d["offered"]), ("bank_rotation", "age", []))
        d = sel.compute("map", self.WHO, [], age=2)      # 2 岁：年龄输入本来就不收，这里只守「范围外不静默分配」
        self.assertEqual(d["rule"], "family_random")
        self.assertEqual([o["family"] for o in d["offered"]], sel.families())
        self.assertTrue(all(o["task_id"] is None and o["pool"] for o in d["offered"]))
        d = sel.compute("map", self.WHO, [], age=9, first_visit=False)
        self.assertEqual(d["rule"], "family_random")

    def test_family_pool_is_the_undone_forms_and_everything_when_all_are_done(self):
        forms = [q["id"] for q in sel.tier_forms("M9")]
        d = sel.compute("map", self.WHO, forms[:1], first_visit=False)
        m9 = next(o for o in d["offered"] if o["family"] == "M9")
        self.assertEqual(m9["pool"], forms[1:])
        d = sel.compute("map", self.WHO, forms, first_visit=False)
        m9 = next(o for o in d["offered"] if o["family"] == "M9")
        self.assertEqual(m9["pool"], forms)
        self.assertTrue(m9["finished"])

    def test_protocol_just_records_the_sequence_and_which_slot_is_open(self):
        seq = [sel.tier_forms("M9")[0]["id"], sel.tier_forms("M6")[0]["id"], "nope"]
        d = sel.compute("protocol", self.WHO, [seq[0]], sequence=seq, seq_index=1)
        self.assertEqual(d["rule"], "protocol")
        self.assertEqual([o["task_id"] for o in d["offered"]], seq[:2])         # 不认识的 id 不进候选
        self.assertEqual([o["locked"] for o in d["offered"]], [True, False])
        self.assertEqual([o["finished"] for o in d["offered"]], [True, False])

    def test_growth_recommends_the_first_family_not_yet_visited_that_trains_the_dimension(self):
        dim = next(iter((QUESTS_BY_ID[sel.tier_forms("M6")[0]["id"]].get("rubric") or {}).get("primary_dimensions") or []), None)
        self.assertTrue(dim)
        d = sel.compute("growth", self.WHO, [], dim=dim)
        self.assertEqual(d["rule"], "recommend_for")
        picked = [o for o in d["offered"] if o["picked"]]
        self.assertEqual(len(picked), 1)
        self.assertNotEqual(picked[0]["family"], "M0")
        # 去过第一个推荐的家族 → 推荐下一个
        been = picked[0]["family"]
        d2 = sel.compute("growth", self.WHO, [sel.tier_forms(been)[0]["id"]], dim=dim)
        picked2 = [o for o in d2["offered"] if o["picked"]]
        if len(d["offered"]) > 1:
            self.assertNotEqual(picked2[0]["family"], been)

    def test_identity_key_prefers_code_over_account_over_device(self):
        self.assertEqual(sel.identity_key({"anon_id": "a", "account_id": "acc-1", "participant_id": "P1"}), "pid:P1")
        self.assertEqual(sel.identity_key({"anon_id": "a", "account_id": "acc-1"}), "acc:acc-1")
        self.assertEqual(sel.identity_key({"anon_id": "a"}), "anon:a")
        self.assertEqual(sel.identity_key({}), "")

    def test_compare_is_set_and_order(self):
        d = sel.compute("map", self.WHO, [], age=9)
        keys = sel.offered_keys(d)
        self.assertEqual(sel.compare(d, keys)["same_order"], True)
        m = sel.compare(d, list(reversed(keys)))
        self.assertEqual((m["same_set"], m["same_order"]), (True, False))
        m = sel.compare(d, keys[:4])
        self.assertEqual((m["same_set"], m["only_server"]), (False, [keys[4]]))


class ShadowEndpoint(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.store = SessionStore()
        self.who = {"anon_id": "anon-shadow-" + __import__("uuid").uuid4().hex[:6]}

    def _options(self, **over):
        body = {"participant": self.who, "entrypoint": "map", "first_visit": True, "age": 9, "age_source": "asked"}
        body.update(over)
        r = self.c.post("/api/task-options", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _finish(self, task_id, sid=None):
        """画完一张（before → finalize），让服务端记下 done。路由记录照客户端在首访地图上的样子带。"""
        body = {"quest_id": task_id, "intent": {"emotion": "", "text": ""}, "participant": self.who,
                "routing": {"age": 9, "age_source": "asked", "band": "B2", "first_visit": True,
                            "bank": (QUESTS_BY_ID.get(task_id) or {}).get("bank") or ""}}
        r = self.c.post("/api/sessions", json=body)
        sid = r.json()["session_id"]
        self.c.post(f"/api/sessions/{sid}/submit", json={"image": _png(), "elapsed_ms": 1000, "phase": "before", "strokes": [_stroke(1)]})
        self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 2000})
        self.assertEqual(self.store.load(sid)["status"], "done")
        return sid

    def test_the_decision_lives_in_a_prepared_ticket_and_is_idempotent_per_input(self):
        server = sel.compute("map", self.who, [], age=9)
        keys = sel.offered_keys(server)
        a = self._options(client_offered=keys, client_new=keys[:2])
        self.assertEqual(a["authority"], "client")            # 默认权威在浏览器；决策块自己标 shadow
        self.assertEqual(self.store.find_decision(a["decision_id"])["authority"], "shadow")
        self.assertEqual(a["offered"], keys)
        self.assertEqual(a["match"]["same_order"], True)
        tid = sel.ticket_of(a["decision_id"])
        t = self.store.load(tid)
        self.assertEqual(t["lifecycle"], "prepared")
        self.assertEqual(t["decision"]["decision_id"], a["decision_id"])
        self.assertEqual(t["decision"]["identity_key"], sel.identity_key(self.who))
        self.assertIsNone(t["decision"]["consumed_by"])
        self.assertEqual(t["offers"][0]["offer_id"], a["offer_id"])
        self.assertEqual(t["offers"][0]["client_new"], keys[:2])
        # 再进一次地图，客户端摆得不一样：同一个决策、新的 offer、对照说不一样
        b = self._options(client_offered=list(reversed(keys)))
        self.assertEqual(b["decision_id"], a["decision_id"])
        self.assertNotEqual(b["offer_id"], a["offer_id"])
        self.assertEqual((b["match"]["same_set"], b["match"]["same_order"]), (True, False))
        self.assertEqual(len(self.store.load(tid)["offers"]), 2)
        # 票不是作品：列表、历史都看不见它
        self.assertNotIn(tid, {r["session_id"] for r in self.store.list()})
        self.assertNotIn(tid, {sid_of(m) for m in iter_sessions()})

    def test_the_server_uses_its_own_done_list_not_the_client_s(self):
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        self.assertEqual(self._options(client_offered=first)["match"]["same_order"], True)
        sid = self._finish(first[0])
        # 历史变了 → 新决策（旧的进 superseded），排位里第一道没了、M9 的进来了
        r = self._options(client_offered=first, client_done=[])
        self.assertNotEqual(r["match"]["same_set"], True)
        self.assertEqual(r["match"]["same_done"], False)
        self.assertEqual(r["offered"][:4], first[1:])
        self.assertEqual(QUESTS_BY_ID[r["offered"][4]]["family"], "M9")
        t = self.store.load(sel.ticket_of(r["decision_id"]))
        self.assertEqual(len(t["superseded"]), 1)
        self.assertEqual(t["superseded"][0]["history"]["n_done"], 0)
        self.assertEqual(t["decision"]["history"]["done_task_ids"], [first[0]])
        self.assertTrue(t["superseded"][0]["superseded_at"])

    def test_creating_a_session_attaches_the_decision_and_consumes_it(self):
        keys = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        a = self._options(client_offered=keys)
        r = self.c.post("/api/sessions", json={
            "quest_id": keys[2], "intent": {"emotion": "", "text": ""}, "participant": self.who,
            "selection": {"entrypoint": "map", "choice_source": "child_click", "decision_id": a["decision_id"],
                          "offer_id": a["offer_id"], "client_offered": keys, "offline": False}})
        self.assertEqual(r.status_code, 201, r.text)
        sid = r.json()["session_id"]
        m = self.store.load(sid)
        s = m["selection"]
        self.assertEqual((s["decision_status"], s["in_offered"], s["authority"], s["source"]), ("attached", True, "client", "client"))
        self.assertEqual((s["entrypoint"], s["choice_source"], s["chosen_task_id"]), ("map", "child_click", keys[2]))
        self.assertEqual(s["decision"]["decision_id"], a["decision_id"])
        self.assertEqual(sel.offered_keys(s["decision"]), keys)
        self.assertEqual(s["offers"][0]["offer_id"], a["offer_id"])
        self.assertEqual(m["quest_id"], keys[2])                      # 题目还是客户端选的那道，服务端没改
        t = self.store.load(sel.ticket_of(a["decision_id"]))
        self.assertEqual(t["decision"]["consumed_by"], sid)
        # 同一个决策再用一次（另一条 session）：already_consumed
        r2 = self.c.post("/api/sessions", json={
            "quest_id": keys[3], "intent": {"emotion": "", "text": ""}, "participant": self.who,
            "selection": {"entrypoint": "map", "choice_source": "child_click", "decision_id": a["decision_id"], "offer_id": a["offer_id"]}})
        s2 = self.store.load(r2.json()["session_id"])["selection"]
        self.assertEqual((s2["decision_status"], s2["consumed_by"]), ("already_consumed", sid))
        self.assertIsNone(s2["decision"])

    def test_a_decision_prepared_for_another_identity_is_not_used(self):
        keys = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        a = self._options(client_offered=keys)
        other = {"anon_id": "anon-other-child"}
        r = self.c.post("/api/sessions", json={
            "quest_id": keys[0], "intent": {"emotion": "", "text": ""}, "participant": other,
            "selection": {"entrypoint": "map", "choice_source": "child_click", "decision_id": a["decision_id"], "offer_id": a["offer_id"]}})
        s = self.store.load(r.json()["session_id"])["selection"]
        self.assertEqual(s["decision_status"], "identity_changed")
        self.assertIsNone(s["decision"])
        self.assertIsNone(self.store.load(sel.ticket_of(a["decision_id"]))["decision"]["consumed_by"])

    def test_no_decision_offline_and_a_pick_outside_the_offered_set(self):
        r = self.c.post("/api/sessions", json={
            "quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""}, "participant": self.who,
            "selection": {"entrypoint": "map", "choice_source": "child_click", "offline": True}})
        s = self.store.load(r.json()["session_id"])["selection"]
        self.assertEqual((s["decision_status"], s["source"], s["decision_id"]), ("none", "client_offline", None))
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""}, "participant": self.who,
                                               "selection": {"decision_id": "dec_000000000000_abcdef"}})
        self.assertEqual(self.store.load(r.json()["session_id"])["selection"]["decision_status"], "missing")
        keys = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        a = self._options(client_offered=keys)
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""}, "participant": self.who,
                                               "selection": {"decision_id": a["decision_id"], "offer_id": a["offer_id"]}})
        s = self.store.load(r.json()["session_id"])["selection"]
        self.assertEqual((s["decision_status"], s["in_offered"]), ("attached", False))

    def test_growth_and_protocol_entrypoints(self):
        dim = next(iter((QUESTS_BY_ID[sel.tier_forms("M6")[0]["id"]].get("rubric") or {}).get("primary_dimensions") or []))
        g = self._options(entrypoint="growth", dim=dim, client_offered=["M6"])
        self.assertEqual(g["rule"], "recommend_for")
        seq = [sel.tier_forms("M9")[0]["id"], sel.tier_forms("M6")[0]["id"]]
        p = self._options(entrypoint="protocol", sequence=seq, seq_index=0, client_offered=seq)
        self.assertEqual((p["rule"], p["offered"], p["match"]["same_order"]), ("protocol", seq, True))

    def test_no_identity_is_refused_and_a_foreign_account_needs_its_token(self):
        self.assertEqual(self.c.post("/api/task-options", json={"participant": {}}).status_code, 400)
        self.assertEqual(self.c.post("/api/task-options", json={"participant": {"anon_id": "x", "account_id": "acc-nope"}}).status_code, 401)

    def test_reap_takes_consumed_and_stale_decision_tickets(self):
        keys = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        a = self._options(client_offered=keys)
        tid = sel.ticket_of(a["decision_id"])
        self.store.reap_tickets(days=30)
        self.assertTrue(self.store.dir(tid).exists())                  # 新鲜、没消费：留着（别的用例留下的消费票可能被收走）
        self.c.post("/api/sessions", json={"quest_id": keys[0], "intent": {"emotion": "", "text": ""}, "participant": self.who,
                                           "selection": {"decision_id": a["decision_id"], "offer_id": a["offer_id"]}})
        self.assertGreaterEqual(self.store.reap_tickets(days=30), 1)   # 消费了：决策已在 session 里，票可以走
        self.assertFalse(self.store.dir(tid).exists())
        b = self._options(client_offered=keys)                        # 新的一张
        tid2 = sel.ticket_of(b["decision_id"])
        self.assertNotEqual(tid2, tid)
        m = self.store.load(tid2); m["issued_at"] = "2020-01-01T00:00:00.000+00:00"; self.store._write(tid2, m)
        self.assertGreaterEqual(self.store.reap_tickets(days=30), 1)   # 放了 30 天没人用：走
        self.assertFalse(self.store.dir(tid2).exists())


class ServerAuthority(unittest.TestCase):
    """PR 4：权威切到服务端（ARTQUEST_SELECTION_AUTHORITY=server）。默认仍是 client，这里当场切、用完切回。"""

    def setUp(self):
        import artquest.config as cfg_mod
        self.cfg = cfg_mod
        self.old = cfg_mod.SELECTION_AUTHORITY
        cfg_mod.SELECTION_AUTHORITY = "server"
        self.c = TestClient(app)
        self.store = SessionStore()
        self.who = {"anon_id": "anon-srv-" + __import__("uuid").uuid4().hex[:6]}

    def tearDown(self):
        self.cfg.SELECTION_AUTHORITY = self.old

    def _options(self, **over):
        body = {"participant": self.who, "entrypoint": "map", "first_visit": True, "age": 9}
        body.update(over)
        r = self.c.post("/api/task-options", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_config_says_so_and_the_server_hands_back_cards_and_draws_the_random_picks(self):
        self.assertEqual(self.c.get("/api/config").json()["selection"], {"authority": "server", "rules_version": sel.RULES_VERSION})
        a = self._options(first_visit=False, client_offered=sel.families())
        self.assertEqual(a["authority"], "server")
        cards = a["cards"]
        self.assertEqual(cards["rule"], "family_random")
        self.assertEqual([c["key"] for c in cards["offered"]], sel.families())
        pools = {o["family"]: o["pool"] for o in self.store.find_decision(a["decision_id"])["offered"]}
        for fam, tid in cards["picks"].items():
            self.assertIn(tid, pools[fam])                                 # 抽的在池子里
        self.assertEqual(len(cards["picks"]), len(sel.families()))
        for c in cards["offered"]:
            self.assertEqual(c["task_id"], cards["picks"][c["family"]])
        b = self._options(first_visit=False, client_offered=sel.families())
        self.assertEqual(b["decision_id"], a["decision_id"])             # 同一个决策
        self.assertNotEqual(b["offer_id"], a["offer_id"])                # 每次展示一条 offer，各有各的抽签
        offers = self.store.offers_of(a["decision_id"])
        self.assertEqual([o["authority"] for o in offers], ["server", "server"])
        self.assertTrue(all(o["picks"] for o in offers))
        # 首访：发回的就是那五个待办位
        f = self._options(client_offered=[])
        self.assertEqual([c["key"] for c in f["cards"]["offered"]], f["offered"])
        self.assertEqual(f["cards"]["locked_more"], True)
        self.assertEqual(f["cards"]["picks"], {})

    def test_the_decision_ticket_becomes_the_session(self):
        keys = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        a = self._options(client_offered=keys)
        tid = sel.ticket_of(a["decision_id"])
        r = self.c.post("/api/sessions", json={
            "quest_id": keys[1], "intent": {"emotion": "", "text": ""}, "participant": self.who,
            "condition": {"ui": "quiet"},
            "selection": {"entrypoint": "map", "choice_source": "child_click", "authority": "server",
                          "decision_id": a["decision_id"], "offer_id": a["offer_id"], "client_offered": keys}})
        self.assertEqual(r.status_code, 201, r.text)
        sid = r.json()["session_id"]
        self.assertEqual(sid, tid, "决策票就是这条 session")
        m = self.store.load(sid)
        self.assertEqual(m["lifecycle"], "recording")
        self.assertEqual(m["quest_id"], keys[1])
        self.assertEqual(m["condition"]["ui"], "quiet", "条件按建 session 时传的算，不沿用票上预算的")
        self.assertNotIn("decision", m)                                  # 顶层不留票的字段
        self.assertNotIn("offers", m)
        s = m["selection"]
        self.assertEqual((s["decision_status"], s["authority"], s["in_offered"], s["ticket_became_session"]), ("attached", "server", True, True))
        self.assertEqual(s["decision"]["consumed_by"], sid)
        self.assertEqual(s["offers"][0]["offer_id"], a["offer_id"])
        self.assertEqual(s["superseded"], [])
        self.assertIn(sid, {row["session_id"] for row in self.store.list()})   # 研究员全量视图里是正式 session 了（孩子视图按空局过滤）
        # 身份的缓存清了：下一次再问是一张新票
        b = self._options(client_offered=keys)
        self.assertNotEqual(sel.ticket_of(b["decision_id"]), tid)

    def test_a_pick_outside_the_offered_set_is_recorded_not_blocked_and_the_ticket_stays(self):
        keys = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        a = self._options(client_offered=keys)
        r = self.c.post("/api/sessions", json={
            "quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""}, "participant": self.who,
            "selection": {"entrypoint": "map", "choice_source": "child_click", "authority": "server",
                          "decision_id": a["decision_id"], "offer_id": a["offer_id"]}})
        self.assertEqual(r.status_code, 201)
        sid = r.json()["session_id"]
        self.assertNotEqual(sid, sel.ticket_of(a["decision_id"]))
        s = self.store.load(sid)["selection"]
        self.assertEqual((s["decision_status"], s["in_offered"]), ("not_in_offered", False))
        self.assertIsNone(s["decision"])
        t = self.store.load(sel.ticket_of(a["decision_id"]))
        self.assertEqual(t["lifecycle"], "prepared")
        self.assertIsNone(t["decision"]["consumed_by"])

    def test_offline_replay_with_an_issued_ticket_copies_the_decision_instead(self):
        keys = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        a = self._options(client_offered=keys)
        t = self.c.post("/api/tickets", json={"n": 1, "participant": self.who}).json()["tickets"][0]
        r = self.c.post("/api/sessions", json={
            "quest_id": keys[0], "session_id": t["session_id"], "intent": {"emotion": "", "text": ""}, "participant": self.who,
            "selection": {"entrypoint": "map", "choice_source": "child_click", "authority": "server_cached",
                          "decision_id": a["decision_id"], "offer_id": a["offer_id"], "offline": True}})
        self.assertEqual(r.status_code, 201, r.text)
        sid = r.json()["session_id"]
        self.assertEqual(sid, t["session_id"])                           # 离线票是这条 session
        s = self.store.load(sid)["selection"]
        self.assertEqual((s["decision_status"], s["authority"], s["source"]), ("attached", "server_cached", "client_offline"))
        self.assertNotIn("ticket_became_session", s)
        self.assertEqual(self.store.load(sel.ticket_of(a["decision_id"]))["decision"]["consumed_by"], sid)
        self.assertEqual(self.store.load(sel.ticket_of(a["decision_id"]))["lifecycle"], "prepared")

    def test_client_mode_never_sends_cards(self):
        self.cfg.SELECTION_AUTHORITY = "client"
        a = self._options(first_visit=False, client_offered=sel.families())
        self.assertEqual(a["authority"], "client")
        self.assertNotIn("cards", a)
        self.assertEqual(self.store.offers_of(a["decision_id"])[0]["picks"], {})


class _ArmBase(unittest.TestCase):
    """策略臂测试的共同底座：权威切到服务端、预算同步跑、模型是假的（httpx.post 换掉）。本身没有用例。"""

    def setUp(self):
        import artquest.config as cfg_mod
        import artquest.main as main_mod
        from artquest import study as study_mod
        from artquest import selection_llm
        from unittest import mock
        self.cfg, self.main, self.study = cfg_mod, main_mod, study_mod
        self.llm = selection_llm.llm
        self.saved = (cfg_mod.SELECTION_AUTHORITY, main_mod.PRECOMPUTE_ASYNC, self.llm.LLM_PROVIDER, self.llm.LLM_BASE_URL,
                      self.llm.LLM_MODEL, list(self.llm._POOL.keys), dict(study_mod.load_study()["condition"]))
        cfg_mod.SELECTION_AUTHORITY = "server"
        main_mod.PRECOMPUTE_ASYNC = False
        self.llm.LLM_PROVIDER, self.llm.LLM_BASE_URL, self.llm.LLM_MODEL = "openai", "https://fake/v1", "fake-model"
        self.llm._POOL.keys = ["sk-fake"]
        study_mod.save_study({"condition": {"selection_policy": "llm"}})
        self.c = TestClient(app)
        self.store = SessionStore()
        self.who = {"anon_id": "anon-arm-" + __import__("uuid").uuid4().hex[:6]}
        self.replies = []            # 假模型按顺序回这些（字符串 = 回复正文）
        self.requests = []
        def post(url, json=None, **k):
            self.requests.append(json)
            if not self.replies:
                raise TimeoutError("read timed out")
            r = self.replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return _FakeResp(r)
        self.patch = mock.patch("httpx.post", post); self.patch.start()
        self.sleep = mock.patch("time.sleep", lambda *_: None); self.sleep.start()

    def tearDown(self):
        self.patch.stop(); self.sleep.stop()
        (self.cfg.SELECTION_AUTHORITY, self.main.PRECOMPUTE_ASYNC, self.llm.LLM_PROVIDER, self.llm.LLM_BASE_URL,
         self.llm.LLM_MODEL, keys, cond) = self.saved
        self.llm._POOL.keys = keys
        self.study.save_study({"condition": cond})

    def _routing(self, task_id):
        return {"age": 9, "age_source": "asked", "band": "B2", "first_visit": True, "bank": (QUESTS_BY_ID.get(task_id) or {}).get("bank") or ""}

    def _finish(self, task_id, abandon=False):
        r = self.c.post("/api/sessions", json={"quest_id": task_id, "intent": {"emotion": "", "text": ""}, "participant": self.who,
                                               "routing": self._routing(task_id)})
        sid = r.json()["session_id"]
        self.c.post(f"/api/sessions/{sid}/log", json={"events": [], "strokes": [_stroke(1)]})
        if abandon:
            self.c.post(f"/api/sessions/{sid}/abandon", json={"elapsed_ms": 900, "reason": "test"})
        else:
            self.c.post(f"/api/sessions/{sid}/submit", json={"image": _png(), "elapsed_ms": 1000, "phase": "before", "strokes": [_stroke(2)]})
            self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 2000})
        return sid

    def _options(self, **over):
        body = {"participant": self.who, "entrypoint": "map", "first_visit": True, "age": 9, "age_source": "asked"}
        body.update(over)
        r = self.c.post("/api/task-options", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

class PolicyArms(_ArmBase):
    """PR 5：selection_policy=llm 时，自由位由模型在冻结候选里排；分到的臂和执行的臂分开记；回退不改分配。"""

    def test_cold_start_and_the_map_path_never_wait_for_the_model(self):
        a = self._options()
        self.assertEqual((a["selection_policy"], a["executed_policy"], a["fallback_reason"]), ("llm", "rules", "cold_start"))
        self.assertEqual(self.requests, [])                                 # 一次模型都没问
        rules = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        self.assertEqual(a["offered"], rules)

    def test_after_a_finished_drawing_the_model_fills_the_free_slot_in_the_background(self):
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        base = sel.compute("map", self.who, [first[0]], age=9)
        pool = sel.pool_for(base)
        self.assertTrue(pool and sel.free_slots(base) == [4])               # 画完一道：第五位是自由位
        choice = pool[-1]                                                   # 规则会给 pool[0]（M9 第一道）；模型偏要最后一个
        self.replies = ['{"ranked": ["%s", "%s"], "why": "练练别的"}' % (choice, pool[0])]
        sid1 = self._finish(first[0])
        self.assertEqual(len(self.requests), 1, "done 落盘后预算了一次，问了模型一次")
        self.assertIn(choice, __import__("json").dumps(self.requests[0], ensure_ascii=False))   # 整个池子都给了模型
        a = self._options(client_offered=first[1:] + [pool[0]])
        self.assertEqual((a["selection_policy"], a["executed_policy"], a["fallback_reason"]), ("llm", "llm", None))
        self.assertEqual(a["offered"], first[1:] + [choice])                 # 固定位照旧，自由位是模型排的
        self.assertEqual(a["match"]["same_order"], False)                    # 客户端按规则摆的，自然对不上
        self.assertEqual(a["cards"]["offered"][4]["task_id"], choice)
        dec = self.store.find_decision(a["decision_id"])
        self.assertEqual(dec["ranking"]["ranked"][0], choice)
        self.assertEqual(dec["ranking"]["why"], "练练别的")
        self.assertEqual(dec["rules_fill"], [pool[0]])
        self.assertTrue(dec["ranking"]["calls"]["call_id"].startswith("call_"))
        calls = self.store.calls(sel.ticket_of(a["decision_id"]))
        self.assertEqual([c["purpose"] for c in calls], ["select"])
        self.assertEqual((calls[0]["execution_kind"], calls[0]["outcome"], calls[0]["stage"]), ("remote", "ok", "bank_rotation"))
        self.assertEqual(len(self.requests), 1, "地图打开只读结果，没有再问")
        # 孩子点了模型排的那道：票成为 session，臂冻进 condition，调用记录跟着走
        r = self.c.post("/api/sessions", json={"quest_id": choice, "intent": {"emotion": "", "text": ""}, "participant": self.who,
                                               "routing": self._routing(choice),
                                               "selection": {"entrypoint": "map", "choice_source": "child_click", "authority": "server",
                                                             "decision_id": a["decision_id"], "offer_id": a["offer_id"]}})
        sid = r.json()["session_id"]
        self.assertEqual(sid, sel.ticket_of(a["decision_id"]))
        m = self.store.load(sid)
        self.assertEqual(m["condition"]["selection_policy"], "llm")
        self.assertEqual((m["selection"]["selection_policy"], m["selection"]["executed_policy"], m["selection"]["in_offered"]), ("llm", "llm", True))
        self.assertEqual([c["purpose"] for c in self.store.calls(sid)], ["select", "personalize"])

    def test_bad_output_falls_back_to_rules_but_keeps_the_arm(self):
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        self.replies = ['{"ranked": ["nope_1", "nope_2"], "why": "x"}', '{"ranked": [], "why": "y"}']
        self._finish(first[0])
        a = self._options()
        rules = sel.offered_keys(sel.compute("map", self.who, [first[0]], age=9))
        self.assertEqual((a["selection_policy"], a["executed_policy"], a["fallback_reason"]), ("llm", "rules", "bad_output"))
        self.assertEqual(a["offered"], rules)
        dec = self.store.find_decision(a["decision_id"])
        self.assertIn("need 1 valid ids", dec["ranking"]["error"])
        self.assertEqual(len(self.requests), 1)

    def test_a_model_timeout_falls_back_and_is_recorded(self):
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        self.replies = []                                                   # 假模型直接超时
        self._finish(first[0])
        a = self._options()
        self.assertEqual((a["executed_policy"], a["fallback_reason"]), ("rules", "timeout"))
        calls = self.store.calls(sel.ticket_of(a["decision_id"]))
        self.assertEqual([c["outcome"] for c in calls], ["exception"])

    def test_abandon_also_precomputes_and_client_authority_never_runs_the_model(self):
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        self.replies = ['{"ranked": [], "why": ""}']
        self._finish(first[0])                                              # 画完一张 → 有历史
        n = len(self.requests)
        self._finish(first[1], abandon=True)                                # 放弃也预算（历史没变但 done 没变 → 同一决策，不重问）
        self.assertEqual(len(self.requests), n)
        self.cfg.SELECTION_AUTHORITY = "client"
        self.replies = ['{"ranked": [], "why": ""}']
        self._finish(first[1])
        a = self._options()
        self.assertEqual((a["selection_policy"], a["executed_policy"], a["fallback_reason"]), ("llm", "rules", "authority_client"))
        self.assertEqual(len(self.requests), n)

    def test_agent_is_reserved_and_rules_is_plain(self):
        self.study.save_study({"condition": {"selection_policy": "agent"}})
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        self._finish(first[0])
        a = self._options()
        self.assertEqual((a["selection_policy"], a["executed_policy"], a["fallback_reason"]), ("agent", "rules", "agent_unavailable"))
        self.study.save_study({"condition": {"selection_policy": "rules"}})
        self._finish(first[1])
        b = self._options()
        self.assertEqual((b["selection_policy"], b["executed_policy"], b["fallback_reason"]), ("rules", "rules", None))
        self.assertEqual(self.requests, [])


class AgentArm(_ArmBase):
    """第三阶段第三步：agent 臂接进预算路径。done 落盘后后台跑循环，地图只读结果；
    ARTQUEST_LLM_TOOLS 没开就是 agent_unavailable，绝不静默跑普通模型。"""

    def setUp(self):
        super().setUp()
        self.cfg.LLM_TOOLS = True
        self.study.save_study({"condition": {"selection_policy": "agent"}})

    def tearDown(self):
        self.cfg.LLM_TOOLS = False
        super().tearDown()

    @staticmethod
    def _tool(name, args):
        import json as _json
        return _json.dumps({"id": "chatcmpl-tool", "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                            "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "",
                                         "tool_calls": [{"id": "tc_1", "type": "function",
                                                         "function": {"name": name, "arguments": _json.dumps(args)}}]}}]})

    def test_the_agent_retrieves_real_history_fixes_an_error_and_its_choice_reaches_the_map(self):
        import json as _json
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        base = sel.compute("map", self.who, [first[0]], age=9)
        pool = sel.pool_for(base)
        choice = pool[-1]
        # 剧本：查 M 族历史（这孩子只画过一张首访题，返回空）→ 提交一个重复的 → 收到错误 → 改好提交
        self.replies = [self._tool("retrieve_history", {"family": "M9"}),
                        self._tool("submit_offer", {"ranked": [choice, choice], "why": "x"}),
                        self._tool("submit_offer", {"ranked": [choice], "why": "换个家族", "evidence": []})]
        # PolicyArms 的假 post 回 _FakeResp(text)；这里的 text 是整段 JSON 回复体，让 json() 原样吐出来
        sid1 = self._finish(first[0])
        self.assertEqual(len(self.requests), 3, "done 落盘后循环跑了三轮")
        a = self._options(client_offered=first[1:] + [pool[0]])
        self.assertEqual((a["selection_policy"], a["executed_policy"], a["fallback_reason"]), ("agent", "agent", None))
        self.assertEqual(a["offered"][4], choice)
        dec = self.store.find_decision(a["decision_id"])
        ag = dec["ranking"]["agent"]
        self.assertEqual(ag["stopped"], "submitted")
        self.assertEqual(ag["counts"], {"rounds": 3, "tool_calls": 3, "retrieve": 1, "validate": 0, "submit": 2, "runtime_validate": 2})
        self.assertEqual([(t["kind"], t.get("tool_name"), t.get("requested_by")) for t in ag["trace"]],
                         [("model", None, None), ("tool", "retrieve_history", "model"), ("model", None, None),
                          ("tool", "validate_offer", "runtime"), ("model", None, None), ("tool", "validate_offer", "runtime")])
        self.assertEqual(ag["trace"][3]["errors"], ["DUPLICATE_TASK"])        # 去重后刚好 1 道，数量没错
        self.assertEqual(dec["history"]["before"], dec["history"]["before"])
        # 决策票的 calls.jsonl：3 条远程（purpose select，各自 operation）+ 3 条工具 local
        calls = self.store.calls(sel.ticket_of(a["decision_id"]))
        remote = [c for c in calls if c["execution_kind"] == "remote"]
        local = [c for c in calls if c["execution_kind"] == "local"]
        self.assertEqual(len(remote), 3)
        self.assertTrue(all(c["purpose"] == "select" and c["prompt_version"] == "agent/v1" for c in remote))
        self.assertEqual([(c["tool_name"], c["requested_by"]) for c in local],
                         [("retrieve_history", "model"), ("validate_offer", "runtime"), ("validate_offer", "runtime")])
        self.assertEqual(local[0]["output"]["source"]["before"], dec["history"]["before"])
        self.assertEqual(local[0]["output"]["n_matched"], 0, "这孩子还没画过 M 族：如实返回空，不编")
        # 第二次请求里有真实的工具返回
        second = [m for m in self.requests[1]["messages"] if m["role"] == "tool"][-1]["content"]
        self.assertIn('"n_matched": 0', second)
        # 孩子点了 agent 排的那道：票成为 session，臂冻进 condition，轨迹跟着走
        r = self.c.post("/api/sessions", json={"quest_id": choice, "intent": {"emotion": "", "text": ""}, "participant": self.who,
                                               "routing": self._routing(choice),
                                               "selection": {"entrypoint": "map", "choice_source": "child_click", "authority": "server",
                                                             "decision_id": a["decision_id"], "offer_id": a["offer_id"]}})
        sid = r.json()["session_id"]
        m = self.store.load(sid)
        self.assertEqual((m["condition"]["selection_policy"], m["selection"]["executed_policy"]), ("agent", "agent"))
        self.assertEqual(m["selection"]["decision"]["ranking"]["agent"]["counts"]["tool_calls"], 3)
        self.assertEqual([c["purpose"] for c in self.store.calls(sid)][:6], ["select"] * 6)

    def test_without_the_tools_switch_the_agent_arm_is_unavailable_and_runs_no_model(self):
        self.cfg.LLM_TOOLS = False
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        self.replies = [self._tool("submit_offer", {"ranked": ["x"], "why": ""})]
        self._finish(first[0])
        a = self._options()
        self.assertEqual((a["selection_policy"], a["executed_policy"], a["fallback_reason"]), ("agent", "rules", "agent_unavailable"))
        self.assertEqual(self.requests, [])

    def test_a_failed_run_keeps_its_trace_and_falls_back_to_rules(self):
        first = sel.offered_keys(sel.compute("map", self.who, [], age=9))
        bad = self._tool("submit_offer", {"ranked": ["nope"], "why": ""})
        self.replies = [bad, bad, bad, bad, bad]
        self._finish(first[0])
        a = self._options()
        rules = sel.offered_keys(sel.compute("map", self.who, [first[0]], age=9))
        self.assertEqual((a["executed_policy"], a["fallback_reason"], a["offered"]), ("rules", "budget_exhausted", rules))
        dec = self.store.find_decision(a["decision_id"])
        self.assertEqual(dec["ranking"]["agent"]["stopped"], "budget_exhausted")
        self.assertEqual(dec["ranking"]["agent"]["counts"]["runtime_validate"], 4)
        self.assertEqual(len(self.requests), 4)

    def test_no_history_is_cold_start_before_any_agent_round(self):
        a = self._options()
        self.assertEqual((a["selection_policy"], a["executed_policy"], a["fallback_reason"]), ("agent", "rules", "cold_start"))
        self.assertEqual(self.requests, [])


class _FakeResp:
    def __init__(self, text, status=200):
        self.status_code = status
        self.text = text
        self.headers = {}

    def json(self):
        # 整段回复体（agent 剧本里的 tool_calls）原样吐；否则当成正文
        if isinstance(self.text, str) and self.text.startswith('{"id": "chatcmpl-tool"'):
            return __import__("json").loads(self.text)
        return {"id": "chatcmpl-fake", "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": self.text}}]}


class Export(unittest.TestCase):
    def test_decisions_csv_one_row_per_session_and_unconsumed_apart(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools import export_dataset
        c = TestClient(app)
        who = {"anon_id": "anon-dec-export"}
        keys = sel.offered_keys(sel.compute("map", who, [], age=9))
        a = c.post("/api/task-options", json={"participant": who, "entrypoint": "map", "age": 9, "client_offered": keys}).json()
        sid = c.post("/api/sessions", json={"quest_id": keys[1], "intent": {"emotion": "", "text": ""}, "participant": who,
                                            "selection": {"entrypoint": "map", "choice_source": "child_click",
                                                          "decision_id": a["decision_id"], "offer_id": a["offer_id"], "client_offered": keys}}).json()["session_id"]
        # 一个没人消费的决策
        b = c.post("/api/task-options", json={"participant": {"anon_id": "anon-dec-unused"}, "entrypoint": "map", "age": 12, "client_offered": []}).json()
        out = Path(tempfile.mkdtemp(prefix="artquest-export-"))
        counts = export_dataset.export(out)
        rows = {r["session_id"]: r for r in csv.DictReader((out / "decisions.csv").open(encoding="utf-8"))}
        r = rows[sid]
        self.assertEqual((r["decision_id"], r["offer_id"], r["decision_status"], r["in_offered"]), (a["decision_id"], a["offer_id"], "attached", "True"))
        self.assertEqual((r["rule"], r["band"], r["chosen_task_id"], r["same_order"]), ("bank_rotation", "B2", keys[1], "True"))
        self.assertEqual(r["offered"], "|".join(keys))
        un = [r for r in csv.DictReader((out / "decisions_unconsumed.csv").open(encoding="utf-8")) if r["decision_id"] == b["decision_id"]]
        self.assertEqual(len(un), 1)
        self.assertEqual((un[0]["session_id"], un[0]["decision_status"], un[0]["band"]), ("", "unconsumed", "B3"))
        # 决策票不是作品
        sess = {r["session_id"] for r in csv.DictReader((out / "sessions.csv").open(encoding="utf-8"))}
        self.assertNotIn(sel.ticket_of(a["decision_id"]), sess)
        self.assertNotIn(sel.ticket_of(b["decision_id"]), sess)
        self.assertGreaterEqual(counts["decisions"], 1)


if __name__ == "__main__":
    unittest.main()
