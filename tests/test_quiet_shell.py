"""对照组（ui=quiet）里也不出现品牌名、空的画廊 tab 和徽章卡（2026-10-19）。

quiet 是去游戏化的那一臂（DESIGN：彩点、闯关路线、徽章、画廊）。彩点收起来之后，还漏着三样：
- 左栏的品牌名「彩绘冒险」；
- 画廊 tab：quiet 下「我的画」那块本来就收着，「大家的画廊」只在 gallery_display=always 时出现，
  两块都不在，点进去是空的一屏；
- 「我的」上的数字卡：徽章那块还摆着（徽章正是 quiet 收起来的东西），「完成的作品」那块还是一扇门，
  通向收起来的画廊。看得见的门不该通向一个藏起来的 tab。

对照：simple 下这三样都在；quiet + gallery_display=always 时画廊 tab 和那扇门照旧在——
证明这条测试量得到它要量的东西，也证明收的只是「点进去是空的」那种情况。

Run:  python3 -m unittest tests.test_quiet_shell -v
"""
import json
import os
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from .env import TMP

from artquest.main import app  # noqa: E402

from .test_browser import _chrome_available, _free_port  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def _shell(page):
    """这一屏上看得见的：品牌名、画廊 tab、徽章卡，以及通向看不见的 tab 的门。"""
    return page.evaluate("""() => {
      const vis = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
                          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'; };
      const pick = sel => [...document.querySelectorAll(sel)].filter(vis);
      return {
        brand: pick('.rail-brand b').length,
        gallery_tab: pick('[data-tab="dex"]').length,
        badge_tile: pick('.stile[data-go="buddy"]').length,
        doors: pick('.stile.jump').map(b => b.dataset.go),
        dead_doors: pick('.stile.jump').map(b => b.dataset.go).filter(go => !pick(`[data-tab="${go}"]`).length),
      };
    }""")


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class QuietHidesTheShell(unittest.TestCase):
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

    def _look(self, condition, pid):
        """study 链接 → 任务页量一次 →「我的」量一次。"""
        study_path = Path(TMP) / "study.json"
        study_path.write_text(json.dumps({"active": True, "study_id": f"shell-{pid}", "condition": condition}),
                              encoding="utf-8")
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
                    page.wait_for_selector("#view-quest:not(.hidden)")
                    page.wait_for_timeout(600)
                    tasks = _shell(page)
                    page.click('[data-tab="me"]')
                    page.wait_for_selector("#view-sessions:not(.hidden)")
                    page.wait_for_selector("#story .stile")
                    page.wait_for_timeout(300)
                    me = _shell(page)
                finally:
                    browser.close()
        finally:
            os.remove(study_path)
        return tasks, me

    def test_quiet_shows_no_brand_no_empty_gallery_tab_and_no_badge_tile(self):
        tasks, me = self._look({"ui": "quiet"}, "S01")
        self.assertEqual((tasks["brand"], tasks["gallery_tab"]), (0, 0), tasks)
        self.assertEqual(me["badge_tile"], 0, me)
        self.assertEqual(me["dead_doors"], [], me)

    def test_control_simple_shows_all_three(self):
        tasks, me = self._look({"ui": "simple"}, "S02")
        self.assertEqual((tasks["brand"], tasks["gallery_tab"]), (1, 1), tasks)
        self.assertEqual(me["badge_tile"], 1, me)
        self.assertIn("dex", me["doors"], me)

    def test_control_quiet_with_a_gallery_keeps_the_gallery_tab_and_its_door(self):
        tasks, me = self._look({"ui": "quiet", "gallery_display": "always"}, "S03")
        self.assertEqual((tasks["brand"], tasks["gallery_tab"]), (0, 1), tasks)
        self.assertIn("dex", me["doors"], me)
        self.assertEqual((me["badge_tile"], me["dead_doors"]), (0, []), me)


if __name__ == "__main__":
    unittest.main()
