"""统一执行记录（calls.jsonl，2026-10-14，agent 级数据计划 PR 1）。

守五件事：
1. 每次真实执行一条：429 重试、JSON 形状不对再要一次、评分没回数字再要一次，各是同一 operation 的下一次 attempt；
   被采用的是最后一条 outcome=ok 的。
2. 九维并行评分：一个 group、每维一个 operation，工作线程里的记录也落到同一个 sink。
3. heuristic / template / 个性化这些本地执行也写同形的一条（execution_kind=local），四个引擎都有。
4. 删掉的 session 不复活：迟到的记录被丢弃、events 追加报错，目录不重建；九个线程同时追加不串行。
5. 导出带 calls.csv + prompts/，sessions.csv 分得清「没采集」和「零次」；新 session 是 schema 4。

Run:  python3 -m unittest -v tests.test_calls
"""
import base64
import hashlib
import importlib
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from .env import TMP as _TMP  # noqa: F401  offline backends + throwaway data dir

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest import config  # noqa: E402
from artquest.main import app  # noqa: E402
from artquest.storage import SessionStore, archive_prompt, prompts_dir, session_calls  # noqa: E402

ECNU = {"ARTQUEST_LLM_BASE_URL": "https://chat.ecnu.edu.cn/open/api/v1",
        "ARTQUEST_LLM_API_KEY": "sk-test", "ARTQUEST_MODEL": "ecnu-plus"}


def _png() -> bytes:
    img = Image.new("RGB", (320, 220), "white")
    ImageDraw.Draw(img).ellipse((40, 40, 220, 180), fill=(150, 190, 235), outline="black", width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


class _Resp:
    def __init__(self, text, status=200):
        self.status_code = status
        self._text = text
        self.text = text if isinstance(text, str) else json.dumps(text)
        self.headers = {"x-request-id": "req-test"}

    def json(self):
        return {"id": "chatcmpl-1", "usage": {"prompt_tokens": 11, "completion_tokens": 3},
                "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": self._text}}]}


def _reload():
    import artquest.config, artquest.llm, artquest.scoring.claude_scorer
    for m in (artquest.config, artquest.llm, artquest.scoring.claude_scorer):
        importlib.reload(m)
    return artquest.llm, artquest.scoring.claude_scorer


# ---------------------------------------------------------------------------
# 1 + 2：远程通路，假 httpx
# ---------------------------------------------------------------------------

class RemoteAttempts(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, ECNU); self.env.start()
        self.llm, self.scorer_mod = _reload()
        self.records = []
        self.systems = []
        self.sleep = mock.patch("time.sleep", lambda *_: None); self.sleep.start()

    def tearDown(self):
        self.sleep.stop(); self.env.stop(); _reload()

    def sink(self, rec, system_text=None):
        self.records.append(rec)
        self.systems.append(system_text)

    @staticmethod
    def fake(replies):
        it = iter(replies)
        def post(url, json=None, **k):
            r = next(it)
            return r if isinstance(r, _Resp) else _Resp(r)
        return post

    def test_a_429_then_ok_is_two_attempts_of_one_operation(self):
        with mock.patch("httpx.post", self.fake([_Resp("busy", 429), "好的"])):
            with self.llm.recording(self.sink, purpose="review", stage="before", prompt_version="v") as ctx:
                text = self.llm.claude_text("system words", [{"type": "text", "text": "hi"}], max_tokens=20)
        self.assertEqual(text, "好的")
        self.assertEqual(len(self.records), 2)
        a, b = self.records
        self.assertEqual((a["attempt"], a["outcome"], a["http_status"]), (1, "http_error", 429))
        self.assertEqual((b["attempt"], b["outcome"], b["http_status"]), (2, "ok", 200))
        self.assertEqual(a["operation_id"], b["operation_id"])
        self.assertEqual(a["group_id"], b["group_id"])
        self.assertNotEqual(a["call_id"], b["call_id"])
        self.assertEqual(ctx.last_call_id, b["call_id"])
        self.assertEqual(ctx.summary()["call_id"], b["call_id"])
        # 远程的那条：谁答的、多少 token、system 只有 hash、正文另交给 sink 归档
        self.assertEqual((b["execution_kind"], b["provider"], b["backend"], b["model"]), ("remote", "openai", "ecnu", "ecnu-plus"))
        self.assertEqual(b["usage"], {"prompt_tokens": 11, "completion_tokens": 3})
        self.assertEqual(b["output"]["text"], "好的")
        self.assertEqual(b["system_hash"], hashlib.sha256("system words".encode()).hexdigest())
        self.assertEqual(b["purpose"], "review")
        self.assertEqual(self.systems[-1], "system words")
        self.assertEqual(b["provider_request_id"], "chatcmpl-1")
        self.assertNotIn("sk-test", json.dumps(self.records))     # key 绝不进记录

    def test_bad_json_then_good_json_is_bad_output_then_ok(self):
        schema = {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer"}}}
        with mock.patch("httpx.post", self.fake(["我觉得是三", '{"n": 3}'])):
            with self.llm.recording(self.sink, purpose="personalize") as ctx:
                obj = self.llm.claude_json("sys", [{"type": "text", "text": "q"}], schema)
        self.assertEqual(obj, {"n": 3})
        self.assertEqual([r["outcome"] for r in self.records], ["bad_output", "ok"])
        self.assertEqual([r["attempt"] for r in self.records], [1, 2])
        self.assertTrue(self.records[0]["error"])
        self.assertEqual(ctx.last_call_id, self.records[1]["call_id"])
        self.assertEqual(len({r["system_hash"] for r in self.records}), 1)

    def test_timeout_is_recorded_as_an_exception_attempt(self):
        def boom(url, json=None, **k):
            raise TimeoutError("read timed out")
        with mock.patch("httpx.post", boom):
            with self.llm.recording(self.sink, purpose="assist") as ctx:
                with self.assertRaises(TimeoutError):
                    self.llm.claude_text("s", [{"type": "text", "text": "x"}], max_tokens=5)
        self.assertEqual(len(self.records), 1)
        self.assertEqual(self.records[0]["outcome"], "exception")
        self.assertIn("timed out", self.records[0]["error"])
        self.assertIsNone(ctx.last_call_id)

    def test_image_input_is_a_sha_reference_not_the_bytes(self):
        png = _png()
        sha = hashlib.sha256(png).hexdigest()
        with mock.patch("httpx.post", self.fake(["ok"])):
            with self.llm.recording(self.sink, purpose="review", images={sha: "before.png"}):
                self.llm.claude_text("s", [self.llm.image_block(png), {"type": "text", "text": "看图"}], max_tokens=5)
        rec = self.records[0]
        self.assertEqual(rec["input"]["images"], [{"sha256": sha, "bytes": len(png), "file": "before.png"}])
        self.assertEqual(rec["input"]["text"], ["看图"])
        self.assertNotIn(base64.b64encode(png).decode()[:40], json.dumps(rec))

    def test_nine_dimension_scoring_is_one_group_one_operation_per_dimension(self):
        quest = {"title": "t", "prompt": "p", "applicable_dims": ["color_contrast", "line_combination", "imagination"]}
        with mock.patch("httpx.post", lambda url, json=None, **k: _Resp("4")):
            with self.llm.recording(self.sink, purpose="score", stage="before") as ctx:
                out = self.scorer_mod.ClaudeScorer().score(_png(), quest, {})
        self.assertEqual({k: v["score"] for k, v in out["dims"].items()},
                         {"color_contrast": 4, "line_combination": 4, "imagination": 4})
        self.assertEqual(len(self.records), 3)                      # 工作线程里的记录也到了同一个 sink
        self.assertEqual(len({r["group_id"] for r in self.records}), 1)
        self.assertEqual(len({r["operation_id"] for r in self.records}), 3)
        self.assertEqual(sorted(r["dimension_id"] for r in self.records), sorted(quest["applicable_dims"]))
        self.assertTrue(all(r["purpose"] == "score" and r["stage"] == "before" for r in self.records))
        self.assertEqual(ctx.count, 3)
        self.assertEqual(set(ctx.adopted), set(quest["applicable_dims"]))
        self.assertEqual(ctx.adopted["imagination"],
                         next(r["call_id"] for r in self.records if r["dimension_id"] == "imagination"))

    def test_no_digit_reply_is_bad_output_and_the_retry_is_adopted(self):
        quest = {"title": "t", "prompt": "p", "applicable_dims": ["imagination"]}
        with mock.patch("httpx.post", self.fake(["我说不好", "3"])):
            with self.llm.recording(self.sink, purpose="score", stage="after") as ctx:
                out = self.scorer_mod.ClaudeScorer().score(_png(), quest, {})
        self.assertEqual(out["dims"]["imagination"]["score"], 3)
        self.assertEqual([(r["attempt"], r["outcome"]) for r in self.records], [(1, "bad_output"), (2, "ok")])
        self.assertIn("no digit", self.records[0]["error"])
        self.assertEqual(ctx.adopted["imagination"], self.records[1]["call_id"])

    def test_nothing_is_recorded_outside_a_recording_context(self):
        with mock.patch("httpx.post", self.fake(["ok"])):
            self.llm.claude_text("s", [{"type": "text", "text": "x"}], max_tokens=5)
        self.assertEqual(self.records, [])


# ---------------------------------------------------------------------------
# 3：离线四个引擎都留下 local 记录（走真接口）
# ---------------------------------------------------------------------------

class LocalEnginesThroughTheApi(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.store = SessionStore()
        self.png = _png()

    def _session(self):
        body = {"quest_id": "imagine_animal", "intent": {"emotion": "开心", "text": "一只在树上睡觉的猫"},
                "participant": {"anon_id": "anon-calls-1"}}
        r = self.c.post("/api/sessions", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["session_id"]

    def test_a_whole_drawing_leaves_one_local_record_per_engine_run(self):
        sid = self._session()
        meta = self.store.load(sid)
        self.assertEqual(meta["schema_version"], 4)
        # 建 session：个性化那一次
        calls = self.store.calls(sid)
        self.assertEqual([c["purpose"] for c in calls], ["personalize"])
        self.assertEqual(calls[0]["execution_kind"], "local")
        self.assertEqual(meta["personalization"]["calls"]["call_id"], calls[0]["call_id"])

        r = self.c.post(f"/api/sessions/{sid}/assist", json={"image": _data_url(self.png), "nth": 1})
        self.assertEqual(r.status_code, 200, r.text)
        assist = r.json()
        self.assertTrue(assist["call_id"].startswith("call_"))
        self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(self.png), "elapsed_ms": 60000, "phase": "before"})
        r = self.c.post(f"/api/sessions/{sid}/submit",
                        json={"image": _data_url(self.png), "elapsed_ms": 120000, "phase": "after", "pending": 0})
        self.assertEqual(r.status_code, 200, r.text)

        calls = self.store.calls(sid)
        self.assertEqual([(c["purpose"], c["stage"]) for c in calls],
                         [("personalize", "create"), ("assist", "during"), ("score", "before"),
                          ("review", "before"), ("score", "after"), ("final", "after")])
        self.assertTrue(all(c["execution_kind"] == "local" for c in calls))
        self.assertTrue(all(c["outcome"] == "ok" for c in calls))
        self.assertTrue(all(c["usage"] is None for c in calls))          # 本地执行没有 token，不伪造
        by = {(c["purpose"], c["stage"]): c for c in calls}
        self.assertEqual(by[("score", "before")]["backend"], "heuristic")
        self.assertEqual(by[("review", "before")]["backend"], "template")
        self.assertEqual(by[("assist", "during")]["output"]["text"], assist["text"])   # 孩子看到的 = 记录里的
        self.assertEqual(by[("assist", "during")]["call_id"], assist["call_id"])
        sha = hashlib.sha256(self.png).hexdigest()
        self.assertEqual(by[("score", "before")]["input"]["images"], [{"sha256": sha, "file": "before.png"}])
        self.assertEqual(by[("final", "after")]["input"]["images"][1], {"sha256": sha, "file": "after.png"})

        # 业务记录指回执行记录
        meta = self.store.load(sid)
        self.assertEqual(meta["before"]["calls"]["group_id"], by[("score", "before")]["group_id"])
        self.assertEqual(meta["before"]["calls"]["call_id"], by[("score", "before")]["call_id"])
        fb = self.store.feedback_log(sid)              # 折叠后的形状：payload 已经摊平
        self.assertEqual(meta["feedback"]["feedback_id"], fb[0]["feedback_id"])
        self.assertEqual(fb[0]["call_id"], by[("review", "before")]["call_id"])
        self.assertEqual(fb[0]["group_id"], by[("review", "before")]["group_id"])
        self.assertEqual(fb[1]["call_id"], by[("final", "after")]["call_id"])
        # 研究员接口的 full 视图里也有
        full = self.c.get(f"/api/sessions/{sid}").json()
        self.assertEqual(len(full["calls"]), 6)

    def test_an_engine_that_blows_up_is_recorded_as_a_local_error(self):
        import artquest.main as m
        sid = self._session()
        orig = m.get_assist_engine
        m.get_assist_engine = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            r = self.c.post(f"/api/sessions/{sid}/assist", json={"image": _data_url(self.png), "nth": 1})
        finally:
            m.get_assist_engine = orig
        self.assertEqual(r.status_code, 200)
        # 2026-10-18：配置的引擎挂了 → 模板顶上；记录里一条 local（backend=template）带 fallback_from / fallback_error
        self.assertEqual(r.json()["backend"], "template")
        self.assertTrue(r.json()["call_id"])
        last = self.store.calls(sid)[-1]
        self.assertEqual((last["purpose"], last["outcome"], last["backend"]), ("assist", "ok", "template"))
        self.assertIn("boom", last["fallback_error"])
        self.assertTrue(last["fallback_from"])
        events = [e for e in self.store.log(sid, "events").read() if e["type"] == "MODEL_FALLBACK"]
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0]["payload"]["purpose"], events[0]["payload"]["to"]), ("assist", "template"))


# ---------------------------------------------------------------------------
# 4：删除后不复活；并发追加不串行
# ---------------------------------------------------------------------------

class StorageGuards(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore()
        self.c = TestClient(app)
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                                                 "participant": {"anon_id": "anon-guard"}})
        self.sid = r.json()["session_id"]

    def _rec(self, i=0):
        return {"call_id": f"call_{i:010d}", "group_id": "grp_x", "operation_id": f"op_{i}", "attempt": 1,
                "purpose": "score", "stage": "before", "dimension_id": "", "execution_kind": "local",
                "backend": "heuristic", "input": {}, "output": {}, "outcome": "ok"}

    def test_a_late_record_for_a_deleted_session_is_dropped_not_resurrected(self):
        d = self.store.dir(self.sid)
        self.assertTrue(self.store.delete(self.sid))
        self.assertIsNone(self.store.add_call(self.sid, self._rec(), "system text"))
        self.assertFalse(d.exists())
        with self.assertRaises(KeyError):
            self.store.log(self.sid, "events").append([{"seq": None, "src": "server", "type": "X", "payload": {}}])
        self.assertFalse(d.exists())

    def test_parallel_appends_from_nine_threads_stay_whole_lines(self):
        def worker(k):
            for j in range(5):
                self.store.add_call(self.sid, self._rec(k * 100 + j))
        ts = [threading.Thread(target=worker, args=(k,)) for k in range(9)]
        [t.start() for t in ts]; [t.join() for t in ts]
        calls = self.store.calls(self.sid)
        # 建 session 时已经有一条 personalize
        mine = [c for c in calls if c["group_id"] == "grp_x"]
        self.assertEqual(len(mine), 45)
        self.assertEqual(len({c["call_id"] for c in mine}), 45)
        raw = (self.store.dir(self.sid) / "calls.jsonl").read_text().splitlines()
        for line in raw:
            json.loads(line)                                         # 每一行都是完整 JSON

    def test_fixed_prompt_text_is_archived_once_by_hash(self):
        text = "你是一个温和的美术老师。" * 3
        h = hashlib.sha256(text.encode()).hexdigest()
        path = archive_prompt(h, text)
        self.assertEqual(path, prompts_dir() / f"{h}.txt")
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        before = path.stat().st_mtime_ns
        archive_prompt(h, text)
        self.assertEqual(path.stat().st_mtime_ns, before)           # 第二次不重写


# ---------------------------------------------------------------------------
# 5：导出
# ---------------------------------------------------------------------------

class Export(unittest.TestCase):
    def test_calls_csv_and_prompts_come_along_and_not_collected_is_distinguishable(self):
        import csv
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools import export_dataset
        c = TestClient(app)
        store = SessionStore()
        sid = c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                                            "participant": {"anon_id": "anon-export"}}).json()["session_id"]
        png = _png()
        c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(png), "elapsed_ms": 1000, "phase": "before"})
        archive_prompt(hashlib.sha256(b"fixed").hexdigest(), "fixed")
        # 一条 schema 3 的旧 session：没有 calls.jsonl
        old = store.dir(sid).parent / "fedcba987654"
        old.mkdir(exist_ok=True)
        (old / "session.json").write_text(json.dumps({"schema_version": 3, "session_id": "fedcba987654",
                                                      "quest_id": "imagine_animal", "status": "done",
                                                      "participant": {"anon_id": "old"}}), encoding="utf-8")
        out = Path(tempfile.mkdtemp(prefix="artquest-export-"))
        counts = export_dataset.export(out)
        self.assertGreaterEqual(counts["calls"], 3)                 # personalize + score + review
        self.assertGreaterEqual(counts["prompts"], 1)
        self.assertTrue((out / "prompts" / f"{hashlib.sha256(b'fixed').hexdigest()}.txt").exists())
        rows = list(csv.DictReader((out / "calls.csv").open(encoding="utf-8")))
        mine = [r for r in rows if r["session_id"] == sid]
        self.assertEqual({r["purpose"] for r in mine}, {"personalize", "score", "review"})
        self.assertTrue(all(r["execution_kind"] == "local" for r in mine))
        sess = {r["session_id"]: r for r in csv.DictReader((out / "sessions.csv").open(encoding="utf-8"))}
        self.assertEqual(sess[sid]["calls_recorded"], "True")
        self.assertEqual(sess[sid]["n_calls"], "3")
        self.assertEqual(sess["fedcba987654"]["calls_recorded"], "False")
        self.assertEqual(sess["fedcba987654"]["n_calls"], "")       # 没采集，不是 0
        self.assertEqual(session_calls(old), [])


if __name__ == "__main__":
    unittest.main()
