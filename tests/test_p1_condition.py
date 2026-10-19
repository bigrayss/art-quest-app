"""成人纸面任务与研究条件（2026-10-19，给成人研究 P1 用）。

P1 的任务文字和量表不进这个公开仓：任务从 `$ARTQUEST_DATA_DIR/tasks.json` 注入，
这里用的全是占位的 fixture。要守的是四件事：

1. tasks.json 能说「参考物是实物，不在屏上」（写生，`stimulus.kind = physical`）
   和「参考图打印给被试」（临摹，`stimulus.kind = printed`，带 `stimulus_id`）——
   两者都冻进 session，屏上都不出现参考图；
2. P1 条件下被试界面没有游戏化元素（彩点、徽章、奖杯），没有任何引擎生成的文字；
3. 不把作品图发给任何外部模型：calls.jsonl 的 execution_kind 全部是 local；
4. 年龄门和首访题库不拦 study 链接进来的成年被试。

Run:  python3 -m unittest tests.test_p1_condition -v
"""
import csv
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from .env import ADMIN, TMP

from fastapi.testclient import TestClient  # noqa: E402

from artquest import config as cfg  # noqa: E402
from artquest import feedback as feedback_mod  # noqa: E402
from artquest import llm  # noqa: E402
from artquest import main as main_mod  # noqa: E402
from artquest import quests as quests_mod  # noqa: E402
from artquest import scoring as scoring_mod  # noqa: E402
from artquest import selection as selection_mod  # noqa: E402
from artquest import study as study_mod  # noqa: E402
from artquest.main import app, store  # noqa: E402
from tools.export_dataset import export  # noqa: E402

from .test_browser import _chrome_available, _free_port  # noqa: E402
from .test_paper_session import PaperClient, anchor, data_url, jpeg_bytes, mark, png_bytes  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

# P1 的固定条件。growth_display=none 是现有条件：不加它，结算页会摆出这张画的九维评分图和评语。
P1 = {"ui": "quiet", "feedback_source": "none", "dialogue_mode": "none", "history_mode": "none",
      "gallery_display": "none", "growth_display": "none", "sync_marks": True, "questionnaire": True,
      "medium": "paper"}

# 占位任务：形状和 P1 的一样，字是假的
FIXTURE_TASKS = [
    {"id": "fx_observe", "title": "Fixture: observe", "prompt": "Fixture prompt (physical object).",
     "type": "fixture", "stimulus": {"kind": "physical", "description": "an object on the table"}},
    {"id": "fx_copy", "title": "Fixture: copy", "prompt": "Fixture prompt (printed reference).",
     "type": "fixture", "stimulus": {"kind": "printed", "stimulus_id": "fx_sheet_a"}},
]


@contextmanager
def tasks_json(rows):
    """把 fixture 任务按 tasks.json 那条路读进来，挂进进程里正在用的任务表；出去时摘掉。

    任务表在 import 时就读好了（`quests.QUESTS`），所以测试里不能只写一个文件——
    读法走 `load_quests()`（和启动时同一条），读到的行挂进各模块手里的那几份表。
    """
    path = Path(TMP) / "tasks.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    try:
        loaded = {q["id"]: q for q in quests_mod.load_quests() if q["id"] in {r["id"] for r in rows}}
    finally:
        os.remove(path)
    lists = {id(m.QUESTS): m.QUESTS for m in (quests_mod, main_mod, study_mod, selection_mod)}
    dicts = {id(m.QUESTS_BY_ID): m.QUESTS_BY_ID for m in (quests_mod, main_mod, study_mod, selection_mod)}
    for q in loaded.values():
        for lst in lists.values():
            lst.append(q)
        for d in dicts.values():
            d[q["id"]] = q
    try:
        yield loaded
    finally:
        for q in loaded.values():
            for lst in lists.values():
                lst.remove(q)
            for d in dicts.values():
                d.pop(q["id"], None)


@contextmanager
def study_json(cfg_):
    path = Path(TMP) / "study.json"
    path.write_text(json.dumps(cfg_), encoding="utf-8")
    try:
        yield
    finally:
        os.remove(path)


def _calls(sid):
    p = store.dir(sid) / "calls.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] if p.exists() else None


class TasksFromTheDataDir(unittest.TestCase):
    """回归护栏：tasks.json 注入和 stimulus 透传在改动前就成立，这里把「够用」写成能失败的检查。"""

    def test_a_task_can_say_its_reference_is_a_real_object_or_a_printout(self):
        with tasks_json(FIXTURE_TASKS) as got:
            obs, cp = got["fx_observe"], got["fx_copy"]
            self.assertEqual(obs["stimulus"]["kind"], "physical")
            self.assertEqual((cp["stimulus"]["kind"], cp["stimulus_id"]), ("printed", "fx_sheet_a"))
            for q in (obs, cp):
                self.assertIsNone(q["reference"], "不在屏上：没有屏上参考图那一项，界面就不摆它")
            c = TestClient(app, headers=ADMIN)
            sids = {}
            for tid in ("fx_observe", "fx_copy"):
                r = c.post("/api/sessions", json={"quest_id": tid, "intent": {"emotion": "", "text": ""},
                                                  "participant": {"anon_id": "anon-p1", "participant_id": "P301"},
                                                  "condition": dict(P1), "canvas": {}})
                self.assertEqual(r.status_code, 201, r.text)
                sids[tid] = r.json()["session_id"]
            snap = store.condition_snapshot(sids["fx_copy"])
            self.assertEqual((snap["stimulus"]["kind"], snap["stimulus_id"]), ("printed", "fx_sheet_a"))
            self.assertEqual(store.condition_snapshot(sids["fx_observe"])["stimulus"]["description"],
                             "an object on the table")
            self.assertFalse((store.dir(sids["fx_copy"]) / "reference").exists())
            with tempfile.TemporaryDirectory() as out:
                export(Path(out))
                with open(Path(out) / "sessions.csv", encoding="utf-8") as fh:
                    rows = {r["session_id"]: r for r in csv.DictReader(fh)}
            self.assertEqual(rows[sids["fx_observe"]]["stimulus_kind"], "physical")
            self.assertEqual(rows[sids["fx_copy"]]["stimulus_kind"], "printed")
            self.assertEqual(rows[sids["fx_copy"]]["stimulus_id"], "fx_sheet_a")

    def test_the_study_sequence_is_only_the_p1_tasks(self):
        with tasks_json(FIXTURE_TASKS), study_json({"active": True, "study_id": "p1fx", "order": "fixed",
                                                    "tasks": ["fx_observe", "fx_copy"], "condition": P1}):
            r = TestClient(app).post("/api/study/assign", json={"participant_id": "P302", "anon_id": "anon-p1"})
            self.assertEqual(r.json()["sequence"], ["fx_observe", "fx_copy"])
            self.assertEqual(r.json()["condition"]["medium"], "paper")


class NoRemoteModel(unittest.TestCase):
    """服务器上配着 key、评分后端是 auto 的最坏情况下，P1 也不把图发出去。

    先跑一条对照（iPad + auto）证明这根探针真的会响，再跑 P1。
    """

    def setUp(self):
        self.c = TestClient(app, headers=ADMIN)
        self.attempts = []

        def refuse(*a, **k):
            self.attempts.append(1)
            raise RuntimeError("a remote model was called")
        for p in (mock.patch.object(cfg, "llm_available", lambda: True),   # 有 key：auto 会去找模型
                  mock.patch.object(llm, "client", refuse),
                  mock.patch.object(llm, "_openai_post", refuse),
                  mock.patch.object(feedback_mod, "FEEDBACK_BACKEND", "auto")):
            p.start()
            self.addCleanup(p.stop)

    def _scorer(self, value):
        p = mock.patch.object(scoring_mod, "SCORER_BACKEND", value)
        p.start()
        self.addCleanup(p.stop)

    def _ipad(self):
        r = self.c.post("/api/sessions", json={
            "quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
            "participant": {"anon_id": "anon-p1"}, "condition": dict(P1, medium="ipad"),
            "canvas": {"width": 1024, "height": 704, "css_width": 900, "css_height": 619}})
        sid = r.json()["session_id"]
        r = self.c.post(f"/api/sessions/{sid}/submit",
                        json={"image": data_url(png_bytes()), "elapsed_ms": 9000, "phase": "before"})
        self.assertEqual(r.status_code, 200, r.text)
        self.c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 9000})
        return sid

    def test_control_the_probe_fires_when_auto_scoring_meets_a_key(self):
        self._scorer("auto")
        sid = self._ipad()
        self.assertTrue(self.attempts, "探针没响：下面两条的「零次」就不可信")
        self.assertIn("remote", {c.get("execution_kind") for c in _calls(sid)})

    def test_a_p1_paper_session_never_reaches_a_model_even_with_auto_scoring(self):
        self._scorer("auto")
        p = PaperClient(self)
        sid = p.create(P1)
        p.run(sid, stages=2)
        self.c.post(f"/api/sessions/{sid}/questionnaire", json={"difficulty": 2, "t_ms": 700_000})
        self.assertEqual(self.attempts, [])
        calls = _calls(sid)
        self.assertTrue(calls, "calls.jsonl 不在 = 没采集，不是零次")
        self.assertEqual({c["execution_kind"] for c in calls}, {"local"})
        self.assertNotIn("score", {c["purpose"] for c in calls}, "纸面作品不打分")
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/assist", json={
            "image": data_url(png_bytes()), "elapsed_ms": 1}).status_code, 403)

    def test_p1_conditions_on_the_ipad_with_the_heuristic_scorer_stay_local(self):
        self._scorer("heuristic")
        sid = self._ipad()
        self.assertEqual(self.attempts, [])
        calls = _calls(sid)
        self.assertEqual({c["execution_kind"] for c in calls}, {"local"})
        self.assertIn("score", {c["purpose"] for c in calls})


def _visible_report(page):
    """这一屏上看得见的游戏化元素和引擎文字。看不见（自己或祖先 display:none）的不算。"""
    return page.evaluate("""() => {
      const vis = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
                          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'; };
      const pick = sel => [...document.querySelectorAll(sel)].filter(vis);
      return {
        view: [...document.querySelectorAll('section.view')].filter(v => !v.classList.contains('hidden')).map(v => v.id),
        mascot: pick('.sprite, #btn-world, .rail-brand .mark').map(e => e.id || e.className.baseVal || e.className),
        badges: pick('#badges-card, .badge, [data-tab="buddy"]').length,
        trophy: pick('#view-final > h1 .ico').length,
        scores: pick('#final-scores, #scores, #score-summary, .rose-wrap').length,
        // 结算页那一句在没有反馈的条件下是写死的系统话（app.js showFinal），不是引擎生成的；别的一律不该出现
        engine_text: pick('#feedback-text, #history-card, #assist, #comparison-text')
                       .map(e => e.innerText.trim()).filter(t => t && t !== '画好了，作品已保存。'),
        age_gate: pick('#age-gate').length,
        buddy_word: document.body.innerText.includes('彩点'),
      };
    }""")


def _assert_clean(test, rep):
    test.assertEqual(rep["mascot"], [], rep)
    test.assertEqual((rep["badges"], rep["trophy"], rep["scores"], rep["age_gate"]), (0, 0, 0, 0), rep)
    test.assertFalse(rep["buddy_word"], rep)
    test.assertEqual(rep["engine_text"], [], rep)


def _events(base, sid):
    req = urllib.request.Request(f"{base}/api/sessions/{sid}", headers=ADMIN)
    return json.load(urllib.request.urlopen(req))["events"]


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class TheParticipantScreens(unittest.TestCase):
    """一台从没开过这个 app 的浏览器，首访题库开着（线上默认），走 study 链接进来。"""

    @classmethod
    def setUpClass(cls):
        import uvicorn
        cls.port = _free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="warning"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + "/api/config", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def setUp(self):
        old = cfg.FIRST_VISIT_BANK
        cfg.FIRST_VISIT_BANK = True
        self.addCleanup(setattr, cfg, "FIRST_VISIT_BANK", old)

    def _ids(self):
        req = urllib.request.Request(self.base + "/api/sessions", headers=ADMIN)
        return {r["session_id"] for r in json.load(urllib.request.urlopen(req))}

    def _walk(self, condition, pid, draw):
        """study 链接 → 任务 → 心愿 → 画（或纸面）→ 问卷 → 结束页。每一屏都量一次。"""
        reports = []
        with tasks_json(FIXTURE_TASKS), study_json({"active": True, "study_id": "p1fx", "order": "fixed",
                                                    "tasks": ["fx_observe", "fx_copy"], "condition": condition}):
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                try:
                    page = browser.new_page(viewport={"width": 1180, "height": 820})
                    page.set_default_timeout(15000)
                    page.goto(f"{self.base}/?study=1&pid={pid}")
                    page.wait_for_selector("#btn-today")
                    page.wait_for_timeout(500)
                    reports.append(_visible_report(page))
                    before = self._ids()
                    page.click("#btn-today")
                    page.wait_for_selector("#view-intent:not(.hidden)")
                    reports.append(_visible_report(page))
                    page.click("#btn-start-draw")
                    draw(page)
                    page.wait_for_selector("#view-survey:not(.hidden)")
                    reports.append(_visible_report(page))
                    page.click("#btn-survey-skip")
                    page.wait_for_function("""() => !document.querySelector('#view-survey:not(.hidden)')""")
                    page.wait_for_timeout(800)
                    reports.append(_visible_report(page))
                    (sid,) = self._ids() - before
                finally:
                    browser.close()
        return sid, reports

    def _paper(self, page):
        page.wait_for_selector("#view-paper:not(.hidden)")
        page.wait_for_selector("#sync-flash.hidden", state="attached")
        self.reports_mid.append(_visible_report(page))
        page.click("#btn-paper-end")
        page.wait_for_selector("#paper-upload:not(.hidden)")
        page.fill("#paper-uploader", "R01")
        page.set_input_files("#paper-final-input", files=[
            {"name": "final.jpg", "mimeType": "image/jpeg", "buffer": jpeg_bytes()}])
        page.wait_for_selector("#btn-paper-done:not([disabled])")
        self.reports_mid.append(_visible_report(page))
        page.click("#btn-paper-done")

    def _ipad(self, page):
        page.wait_for_selector("#view-draw:not(.hidden)")
        page.wait_for_selector("#sync-flash.hidden", state="attached")
        self.reports_mid.append(_visible_report(page))
        box = page.eval_on_selector("#canvas", "e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
        x, y, w, h = box
        page.mouse.move(x + w * .3, y + h * .4)
        page.mouse.down()
        page.mouse.move(x + w * .6, y + h * .6, steps=10)
        page.mouse.up()
        page.wait_for_timeout(300)
        page.click("#btn-submit")

    def test_a_p1_paper_participant_sees_no_mascot_badges_or_engine_text(self):
        self.reports_mid = []
        sid, reports = self._walk(P1, "P311", self._paper)
        reports[2:2] = self.reports_mid
        for rep in reports:
            _assert_clean(self, rep)
        self.assertEqual(reports[0]["view"], ["view-quest"], "年龄门和首访题库没拦路，直接到任务")
        self.assertEqual(reports[-1]["view"], ["view-paper"])
        evs = _events(self.base, sid)
        self.assertEqual([e for e in evs if e["type"] == "MASCOT_STATE"], [], "没出现的精灵不记曝光")

    def test_the_same_conditions_on_the_ipad_are_just_as_quiet(self):
        self.reports_mid = []
        sid, reports = self._walk(dict(P1, medium="ipad"), "P312", self._ipad)
        reports[2:2] = self.reports_mid
        for rep in reports:
            _assert_clean(self, rep)
        self.assertEqual(reports[-1]["view"], ["view-final"])
        self.assertEqual([e for e in _events(self.base, sid) if e["type"] == "MASCOT_STATE"], [])


if __name__ == "__main__":
    unittest.main()
