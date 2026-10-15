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
        """画完一张（before → finalize），让服务端记下 done。"""
        body = {"quest_id": task_id, "intent": {"emotion": "", "text": ""}, "participant": self.who}
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
        self.assertEqual(a["authority"], "shadow")
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
