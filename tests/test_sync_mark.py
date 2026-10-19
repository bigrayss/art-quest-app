"""同步标记与客户端时钟锚点（2026-10-19）。

一条时间线、一个时钟——但「这条时间线的 0 在墙上是几点」原来是服务端回答的：
`times.started_at` 是服务端收到建 session 请求的那一刻，`t_ms` 的零点是客户端
拿到响应之后的 `Date.now()`。两者差一次往返，再加两台机器的钟差；离线票补建时，
差的是画完到联网之间的整段时间。

所以客户端在零点记一条 `SYNC_MARK`（n=0）：t_ms 和 wall_ms 出自同一次 `Date.now()`，
锚点 = wall_ms − t_ms，从头到尾只用客户端那一只钟。n≥1 是看得见的同步标记
（整屏白闪一下、显示编号），只在 `sync_marks` 条件打开时才有，给眼动眼镜的
场景相机和俯拍相机对帧用。

Run:  python3 -m unittest tests.test_sync_mark -v
"""
import csv
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from .env import ADMIN, TMP

from fastapi.testclient import TestClient  # noqa: E402

from artquest import events as ev  # noqa: E402
from artquest import study as study_mod  # noqa: E402
from artquest.main import app  # noqa: E402
from tools.export_dataset import export  # noqa: E402

from .test_browser import _chrome_available, _free_port  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

WALL0 = 1_760_000_000_000      # an arbitrary client wall clock, ms since epoch


def _anchor(t_ms=3, wall_ms=WALL0 + 3, seq=1):
    return {"seq": seq, "t_ms": t_ms, "type": "SYNC_MARK",
            "payload": {"n": 0, "source": "clock", "visible": False, "wall_ms": wall_ms}}


def _mark(n, t_ms, seq, source="researcher"):
    return {"seq": seq, "t_ms": t_ms, "type": "SYNC_MARK",
            "payload": {"n": n, "source": source, "visible": True}}


class Vocabulary(unittest.TestCase):
    def test_sync_mark_is_a_known_event(self):
        self.assertTrue(ev.is_known("SYNC_MARK"))
        self.assertEqual(ev.unknown_types(["SYNC_MARK", "STROKE_END"]), set())


class ClientClockAnchor(unittest.TestCase):
    def test_the_anchor_is_wall_minus_t_from_the_same_reading(self):
        self.assertEqual(ev.client_clock_anchor([_anchor(t_ms=3, wall_ms=WALL0 + 3)]), WALL0)

    def test_visible_marks_are_not_the_anchor(self):
        """可见标记不带 wall_ms，就算带了也不当锚点：锚点只有 n=0 那一条。"""
        marks = [dict(_mark(1, 900, 2), payload={"n": 1, "source": "start", "visible": True, "wall_ms": 5}),
                 _anchor(seq=1)]
        self.assertEqual(ev.client_clock_anchor(marks), WALL0)

    def test_no_anchor_is_none_not_zero(self):
        """改版之前的 session 没有这条：那是「没采集」，不是 1970 年。"""
        self.assertIsNone(ev.client_clock_anchor([]))
        self.assertIsNone(ev.client_clock_anchor([{"seq": 1, "t_ms": 0, "type": "SESSION_START", "payload": {}}]))

    def test_the_first_anchor_wins(self):
        later = _anchor(t_ms=10, wall_ms=WALL0 + 999, seq=7)
        self.assertEqual(ev.client_clock_anchor([_anchor(seq=1), later]), WALL0)


class ConditionAndExport(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app, headers=ADMIN)

    def _create(self, condition=None):
        body = {"quest_id": "imagine_animal", "intent": {"emotion": "", "text": ""},
                "participant": {"anon_id": "anon-sync", "participant_id": "P090"},
                "condition": condition or {},
                "canvas": {"width": 1024, "height": 704, "css_width": 900, "css_height": 619}}
        r = self.c.post("/api/sessions", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["session_id"]

    def test_sync_marks_is_off_by_default_and_frozen(self):
        self.assertIs(study_mod.DEFAULT_CONDITION["sync_marks"], False)
        sid = self._create()
        self.assertIs(self.c.get(f"/api/sessions/{sid}").json()["condition"]["sync_marks"], False)
        sid = self._create({"sync_marks": True})
        self.assertIs(self.c.get(f"/api/sessions/{sid}").json()["condition"]["sync_marks"], True)

    def test_export_carries_the_client_anchor_and_the_visible_marks(self):
        sid = self._create({"sync_marks": True})
        batch = {"events": [_anchor(seq=1), _mark(1, 40, 2, "start"), _mark(2, 8000, 3), _mark(3, 15000, 4, "submit")]}
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/log", json=batch).status_code, 200)
        old = self._create()          # a client from before the anchor existed: no SYNC_MARK at all
        with tempfile.TemporaryDirectory() as out:
            export(Path(out))
            with open(Path(out) / "sessions.csv", encoding="utf-8") as fh:
                rows = {r["session_id"]: r for r in csv.DictReader(fh)}
        self.assertEqual(rows[sid]["client_started_at_ms"], str(WALL0))
        self.assertEqual(rows[sid]["n_sync_marks"], "3")
        self.assertEqual(rows[sid]["cond_sync_marks"], "True")
        self.assertEqual(rows[old]["client_started_at_ms"], "")
        self.assertEqual(rows[old]["n_sync_marks"], "", "没有锚点的客户端没采过标记：空，不是 0")


def _session_events(base, sid):
    req = urllib.request.Request(f"{base}/api/sessions/{sid}", headers=ADMIN)
    return json.load(urllib.request.urlopen(req))["events"]


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class InTheBrowser(unittest.TestCase):
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
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def _ids(self):
        req = urllib.request.Request(self.base + "/api/sessions", headers=ADMIN)
        return {r["session_id"] for r in json.load(urllib.request.urlopen(req))}

    def _marks(self, sid, want, timeout=12.0):
        """Wait until `want` SYNC_MARKs have been flushed to the server."""
        end = time.time() + timeout
        while True:
            marks = [e for e in _session_events(self.base, sid) if e["type"] == "SYNC_MARK"]
            if len(marks) >= want or time.time() > end:
                return sorted(marks, key=lambda e: e["payload"]["n"])
            time.sleep(0.3)

    def _page(self, browser):
        page = browser.new_page(viewport={"width": 1180, "height": 820})
        page.set_default_timeout(15000)
        page.add_init_script("""
          localStorage.setItem('artquest.tour/2', '1'); localStorage.setItem('artquest.acct_prompted', '1');
          sessionStorage.setItem('artquest.entered', '1');
        """)
        return page

    def test_every_session_anchors_the_client_clock_and_shows_no_sync_button(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            try:
                page = self._page(browser)
                page.goto(self.base)
                page.wait_for_selector("#quest-grid .quest-card")
                before_ids = self._ids()
                t_before = page.evaluate("Date.now()")
                page.click("#quest-grid .quest-card")
                page.click("#btn-today")
                page.wait_for_selector("#view-draw:not(.hidden)")
                t_after = page.evaluate("Date.now()")
                self.assertTrue(page.is_hidden("#btn-sync"), "没开 sync_marks，孩子面前不该有同步钮")
                (sid,) = self._ids() - before_ids
                marks = self._marks(sid, 1)
                self.assertEqual(len(marks), 1, marks)
                p = marks[0]["payload"]
                self.assertEqual((p["n"], p["source"], p["visible"]), (0, "clock", False))
                anchor = ev.client_clock_anchor(marks)
                self.assertTrue(t_before <= anchor <= t_after, (t_before, anchor, t_after))
                self.assertLess(marks[0]["t_ms"], 2000, "锚点要记在零点附近")
            finally:
                browser.close()

    def test_with_sync_marks_on_the_screen_flashes_numbered_marks(self):
        study_path = Path(TMP) / "study.json"
        study_path.write_text(json.dumps({"active": True, "study_id": "sync1",
                                          "condition": {"sync_marks": True}}), encoding="utf-8")
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                try:
                    page = self._page(browser)
                    page.goto(self.base + "/?study=1&pid=P91")
                    page.wait_for_selector("#quest-grid .quest-card")
                    page.wait_for_selector("#studybar:not(.hidden)")
                    page.wait_for_timeout(600)
                    before_ids = self._ids()
                    page.eval_on_selector("#quest-grid .quest-card:not(.locked)", "e => e.click()")
                    page.click("#btn-today")
                    page.wait_for_selector("#view-draw:not(.hidden)")
                    # 开始那一下自己闪：编号 1
                    page.wait_for_selector("#sync-flash:not(.hidden)")
                    self.assertEqual(page.inner_text("#sync-flash").strip(), "1")
                    page.wait_for_selector("#sync-flash.hidden", state="attached")
                    self.assertTrue(page.is_visible("#btn-sync"))
                    page.click("#btn-sync")
                    page.wait_for_selector("#sync-flash:not(.hidden)")
                    self.assertEqual(page.inner_text("#sync-flash").strip(), "2")

                    (sid,) = self._ids() - before_ids
                    marks = self._marks(sid, 3)
                    got = [(m["payload"]["n"], m["payload"]["source"], m["payload"]["visible"]) for m in marks]
                    self.assertEqual(got, [(0, "clock", False), (1, "start", True), (2, "researcher", True)])
                    self.assertLess(marks[1]["t_ms"], marks[2]["t_ms"])
                    for m in marks[1:]:
                        self.assertNotIn("wall_ms", m["payload"], "能算出来的不存：墙钟 = 锚点 + t_ms")
                finally:
                    browser.close()
        finally:
            os.remove(study_path)


if __name__ == "__main__":
    unittest.main()
