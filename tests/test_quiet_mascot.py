"""对照组（ui=quiet）里彩点整个不出现，也不记 MASCOT_STATE（2026-10-19）。

quiet 是去游戏化的那一臂。修之前有两处漏：结算页的 `.buddy-head` 被
`#view-final .buddy-head` 盖过（ID 选择器更具体），彩点照样露脸；任务卡、反馈页、
等待层上的精灵 `.sprite` 从来没收过。精灵不出现，时间线上也就不该有一条 MASCOT_STATE 曝光。

对照：同一条路走 simple，彩点看得见、MASCOT_STATE 记得到——证明这条测试量得到它要量的东西。

Run:  python3 -m unittest tests.test_quiet_mascot -v
"""
import json
import os
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from .env import ADMIN, TMP

from artquest.main import app  # noqa: E402

from .test_browser import _chrome_available, _free_port  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

MASCOT = ".sprite, .buddy-head, #btn-world, .rail-brand .mark, #view-final > h1 .ico"


def _visible_mascots(page):
    return page.evaluate("""(sel) => [...document.querySelectorAll(sel)].filter(el => {
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden';
      }).map(e => e.id || (e.className && e.className.baseVal) || e.className)""", MASCOT)


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class QuietHidesTheMascot(unittest.TestCase):
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

    def _events(self, sid):
        req = urllib.request.Request(f"{self.base}/api/sessions/{sid}", headers=ADMIN)
        return json.load(urllib.request.urlopen(req))["events"]

    def _walk(self, ui, pid):
        """study 链接 → 画一笔 → 交 → 反馈页 → 保留原样 → 结算页。每一屏量一次看得见的彩点。"""
        study_path = Path(TMP) / "study.json"
        study_path.write_text(json.dumps({"active": True, "study_id": f"quiet-{ui}", "condition": {"ui": ui}}),
                              encoding="utf-8")
        seen = {}
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                try:
                    page = browser.new_page(viewport={"width": 1180, "height": 820})
                    page.set_default_timeout(15000)
                    page.add_init_script("localStorage.setItem('artquest.tour/2','1');"
                                         "localStorage.setItem('artquest.acct_prompted','1');"
                                         "sessionStorage.setItem('artquest.entered','1');")
                    page.goto(f"{self.base}/?study=1&pid={pid}")
                    page.wait_for_selector("#studybar:not(.hidden)")
                    page.wait_for_timeout(600)
                    before = self._ids()
                    page.eval_on_selector("#quest-grid .quest-card:not(.locked)", "e => e.click()")
                    page.click("#btn-today")
                    # quiet 多一页心愿（simple 没有），那一页上的精灵也要量
                    page.wait_for_selector("#view-draw:not(.hidden), #view-intent:not(.hidden)")
                    if page.is_visible("#view-intent"):
                        page.wait_for_timeout(400)
                        seen["intent"] = _visible_mascots(page)
                        page.click("#btn-start-draw")
                    page.wait_for_selector("#view-draw:not(.hidden)")
                    page.wait_for_timeout(400)
                    seen["draw"] = _visible_mascots(page)
                    x, y, w, h = page.eval_on_selector(
                        "#canvas", "e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
                    page.mouse.move(x + w * .3, y + h * .4)
                    page.mouse.down()
                    page.mouse.move(x + w * .6, y + h * .6, steps=10)
                    page.mouse.up()
                    page.wait_for_timeout(300)
                    page.click("#btn-submit")
                    page.wait_for_selector("#view-result:not(.hidden)")
                    page.wait_for_timeout(400)
                    seen["result"] = _visible_mascots(page)
                    page.click("#btn-skip-revise")
                    page.wait_for_selector("#view-final:not(.hidden)")
                    page.wait_for_timeout(800)
                    seen["final"] = _visible_mascots(page)
                    (sid,) = self._ids() - before
                    # 让发件箱把最后一批事件送到
                    page.wait_for_function("async () => (await ArtLog.pending()) === 0", timeout=10000)
                finally:
                    browser.close()
        finally:
            os.remove(study_path)
        return sid, seen

    def test_quiet_shows_no_mascot_on_any_screen_and_logs_no_exposure(self):
        sid, seen = self._walk("quiet", "Q01")
        self.assertEqual({k: v for k, v in seen.items() if v}, {}, seen)
        self.assertTrue({"draw", "result", "final"} <= set(seen), seen)
        self.assertEqual([e for e in self._events(sid) if e["type"] == "MASCOT_STATE"], [])

    def test_control_simple_shows_the_mascot_and_logs_it(self):
        sid, seen = self._walk("simple", "Q02")
        self.assertTrue(any(seen.values()), f"simple 下应当看得见彩点，否则这条测试量不到东西：{seen}")
        self.assertTrue([e for e in self._events(sid) if e["type"] == "MASCOT_STATE"])


if __name__ == "__main__":
    unittest.main()
