"""专业版：另一套画笔引擎、图层、自定义画布——以及「按日志能把画逐像素重建出来」。

真浏览器里画一张（换笔、加图层、改混合模式、撤销重做、隐藏、合并、橡皮），
然后只凭服务器上的日志重放，和浏览器画布上的像素逐个比。
"""
import base64
import io
import json
import shutil
import threading
import time
import unittest
import urllib.request

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

from . import test_browser as tb
from .env import ADMIN

SHOT = None      # 调试时填一个路径，画完存一张截图


class ProEdition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn

        from artquest.main import app
        cls.port = tb._free_port()
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

    def _get(self, path):
        return json.load(urllib.request.urlopen(urllib.request.Request(self.base + path, headers=ADMIN)))

    def _ids(self):
        return {r["session_id"] for r in self._get("/api/sessions")}

    def _paint(self, page, size="1200x900"):
        page.add_init_script(f"localStorage.setItem('artquest.edition','pro'); localStorage.setItem('artquest.canvas','{size}')")
        tb.ZoomKeepsStrokesInCanvasSpace._start(self, page, "")
        return tb.ZoomKeepsStrokesInCanvasSpace._canvas_tools(page)

    @unittest.skipUnless(shutil.which("node"), "重放要 Node")
    def test_a_pro_drawing_is_rebuilt_pixel_for_pixel_from_its_log(self):
        from artquest.config import SESSIONS_DIR
        from artquest.reconstruct import check_final, paint_ops, rebuild
        from artquest.storage import session_events, session_strokes

        errors, before = [], self._ids()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.on("pageerror", lambda e: errors.append(str(e)))
            screen_of, drag, stroke_from = self._paint(page)

            geom = page.evaluate("() => { const c = document.querySelector('#canvas'); return [c.width, c.height, document.body.classList.contains('pro')] }")
            self.assertEqual(geom, [1200, 900, True])
            tools = page.eval_on_selector_all("#tools button", "e=>e.map(b=>b.dataset.tool)")
            self.assertEqual(tools, ["pencil", "charcoal", "ink", "wash", "oil", "eraser"])

            def curve(cx, cy, w, bend):
                a = screen_of(cx, cy)
                page.mouse.move(*a)
                page.mouse.down()
                for i in range(1, 13):
                    page.mouse.move(a[0] + w * i / 12, a[1] + bend * (i / 12) * (1 - i / 12) * 4)
                page.mouse.up()

            for n, tool in enumerate(["pencil", "charcoal", "ink", "wash"]):
                page.click(f'#tools [data-tool="{tool}"]')
                curve(120, 120 + n * 90, 380, 30)

            page.click("#btn-layers")
            page.click("#lp-add")                                # 图层 2
            page.click('#tools [data-tool="oil"]')
            curve(150, 560, 360, -40)
            curve(250, 480, 60, 120)
            page.select_option("#lp-blend", "multiply")
            page.click('#tools [data-tool="ink"]')
            curve(520, 300, 300, 60)                             # 这一笔会被撤销
            page.keyboard.press("Control+z")
            curve(560, 620, 300, -60)                            # 这一笔撤销后又重做
            page.keyboard.press("Control+z")
            page.keyboard.press("Control+Shift+z")
            page.click("#lp-list .lp-row.active .lp-eye")        # 藏起来
            page.click("#lp-list .lp-row.active .lp-eye")        # 再露出来
            page.click("#lp-add")                                # 图层 3
            page.click('#tools [data-tool="pencil"]')
            curve(700, 150, 300, 50)
            page.click("#lp-merge")                              # 图层 3 压进图层 2
            page.click('#tools [data-tool="eraser"]')
            curve(140, 300, 500, 10)                             # 现在在图层 2 上擦：底下图层 1 的淡墨不该被擦掉
            page.wait_for_timeout(300)

            if SHOT:
                page.screenshot(path=SHOT)
            layers = page.eval_on_selector_all("#lp-list .lp-row", "e=>e.map(r=>r.dataset.layer)")
            url = page.evaluate("() => document.querySelector('#canvas').toDataURL('image/png')")
            page.evaluate("ArtLog.flush()")
            page.wait_for_timeout(1200)
            browser.close()

        self.assertEqual(errors, [])
        self.assertEqual(layers, ["L2", "L1"])
        sid = (self._ids() - before).pop()
        d = SESSIONS_DIR / sid
        strokes, events = session_strokes(d), session_events(d)

        # every stroke says which layer, which seed, which engine
        self.assertEqual(len(strokes), 10)
        for s in strokes:
            self.assertEqual(s["engine"], "paint/1")
            self.assertTrue(s["seed"])
        self.assertEqual([s["layer"] for s in strokes], ["L1"] * 4 + ["L2"] * 4 + ["L3", "L2"])

        kinds = [op["kind"] for op in paint_ops(events, strokes)]
        # the undone stroke is gone, the redone one is back, and the layer steps sit between the strokes
        self.assertEqual(kinds, ["stroke"] * 4 + ["layer_add", "stroke", "stroke", "layer_props", "stroke",
                                 "layer_props", "layer_props", "layer_add", "stroke", "layer_merge", "stroke"])

        built = rebuild(d)
        self.assertEqual((built["engine"], built["replayed"]), ("paint/1", "node"))
        self.assertEqual(built["size"], (1200, 900))
        on_screen = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
        diff = ImageChops.difference(built["image"], on_screen).getbbox()
        self.assertIsNone(diff, f"replay and screen differ inside {diff}")
        # and it is a drawing, not a blank sheet that trivially matches
        self.assertGreater(len(on_screen.getcolors(maxcolors=1 << 24)), 500)
        self.assertTrue(built["process"], "no process frames")

        (d / "final.png").write_bytes(base64.b64decode(url.split(",", 1)[1]))
        self.assertTrue(check_final(d, built)["exact"])

    def test_a_tall_canvas_is_shown_whole(self):
        """自定义画布不是 1024:704 了：竖幅的也得整张看得见、不变形，落笔还在笔尖底下。"""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            screen_of, drag, stroke_from = self._paint(page, "1536x2048")
            page.wait_for_timeout(400)
            box = page.evaluate("""() => { const r = document.querySelector('#canvas').getBoundingClientRect(),
                v = document.querySelector('#viewport').getBoundingClientRect(), d = document.querySelector('#view-draw .dock').getBoundingClientRect();
                return {c: [r.left, r.top, r.right, r.bottom], v: [v.left, v.top, v.right, v.bottom], dockTop: d.top, vh: innerHeight} }""")
            page.click('#tools [data-tool="ink"]')
            stroke_from(768, 1024, 60, 0)
            if SHOT:
                page.screenshot(path=SHOT)
            dark = page.evaluate("""() => { const c = document.querySelector('#canvas');
                const d = c.getContext('2d').getImageData(790, 1024, 1, 1).data; return d[0] + d[1] + d[2] }""")
            browser.close()
        c, v = box["c"], box["v"]
        self.assertAlmostEqual((c[2] - c[0]) / (c[3] - c[1]), 1536 / 2048, delta=0.01)      # 没被拉伸
        for i in (0, 1):
            self.assertGreaterEqual(c[i], v[i] - 1)
        for i in (2, 3):
            self.assertLessEqual(c[i], v[i] + 1)                                            # 没被框切掉
        self.assertLessEqual(c[3], box["dockTop"] + 1)
        self.assertLess(box["dockTop"], box["vh"])
        self.assertLess(dark, 600, "the stroke did not land under the pointer")

    def test_the_daily_edition_is_untouched(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.add_init_script("localStorage.setItem('artquest.canvas','2048x2048')")   # 只有专业版认这个
            tb.ZoomKeepsStrokesInCanvasSpace._start(self, page, "")
            got = page.evaluate("""() => { const c = document.querySelector('#canvas');
                return [c.width, c.height, document.body.classList.contains('pro'),
                        [...document.querySelectorAll('#tools button')].map(b => b.dataset.tool).join(),
                        document.querySelector('#btn-layers').classList.contains('hidden')] }""")
            browser.close()
        self.assertEqual(got, [1024, 704, False, "pencil,brush,marker,eraser", True])


if __name__ == "__main__":
    unittest.main()
