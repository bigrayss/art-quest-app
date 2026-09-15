"""The one property no Python test can prove: zoom must not move the data.

Zoom and pan are a CSS transform on the canvas element. Stroke points are read
through `getBoundingClientRect()`, which reports the *transformed* box, so they
should stay in canvas pixel space at any zoom level — and replay, undo and QC
stay untouched. "Should" is doing a lot of work in that sentence, so this drives
a real browser and checks the coordinates that actually get logged.

Skipped unless Playwright and a Chrome build are both available:

    .venv/bin/pip install playwright          # chrome itself is the system one
    .venv/bin/python -m unittest tests.test_browser -v
"""
import json
import socket
import threading
import time
import unittest
import urllib.request

from .env import TMP as _TMP  # noqa: F401  (offline backends, throwaway data dir)

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _chrome_available() -> bool:
    if sync_playwright is None:
        return False
    try:
        with sync_playwright() as pw:
            pw.chromium.launch(channel="chrome").close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class ZoomKeepsStrokesInCanvasSpace(unittest.TestCase):
    """Draw at 1x, at max zoom, and after a pan — every point must land true."""

    @classmethod
    def setUpClass(cls):
        import uvicorn

        from artquest.main import app
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

    def _get(self, path):
        return json.load(urllib.request.urlopen(self.base + path))

    def _ids(self):
        return {r["id"] for r in self._get("/api/sessions")}

    def _start(self, page, intent, family=None):
        """Walk the real UI from the mission map into a running session."""
        page.set_default_timeout(15000)
        page.goto(self.base)
        # `.quest-card` alone would resolve to the hidden card inside the draw
        # view before /api/quests lands, and a locator never re-queries
        page.wait_for_selector("#quest-grid .quest-card")
        if family:
            titles = page.eval_on_selector_all("#quest-grid .quest-card h3", "e=>e.map(x=>x.textContent)")
            page.eval_on_selector_all("#quest-grid .quest-card", f"(e)=>e[{titles.index(family)}].click()")
        else:
            page.click("#quest-grid .quest-card")
        page.click("#emotion-chips button")
        page.fill("#intent-text", intent)
        page.click("#btn-start-draw")
        page.wait_for_selector("#view-draw:not(.hidden)")

    @staticmethod
    def _canvas_tools(page):
        def screen_of(cx, cy):
            """Where canvas pixel (cx, cy) sits on screen right now."""
            return page.evaluate("""([cx, cy]) => {
                const c = document.querySelector('#canvas'), r = c.getBoundingClientRect();
                return [r.left + cx * r.width / c.width, r.top + cy * r.height / c.height];
            }""", [cx, cy])

        def drag(a, dx, dy):
            page.mouse.move(*a)
            page.mouse.down()
            page.mouse.move(a[0] + dx, a[1] + dy, steps=8)
            page.mouse.up()

        def stroke_from(cx, cy, dx, dy):
            drag(screen_of(cx, cy), dx, dy)

        return screen_of, drag, stroke_from

    def test_strokes_land_in_canvas_pixels_at_every_zoom(self):
        errors, before = [], self._ids()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("pageerror", lambda e: errors.append(str(e)))
            self._start(page, "zoom invariant")
            screen_of, drag, stroke_from = self._canvas_tools(page)

            stroke_from(200, 200, 90, 60)                     # 1. baseline at 100 %

            page.mouse.move(*screen_of(700, 500))             # 2. wheel-zoom over a spot
            for _ in range(12):
                page.mouse.wheel(0, -120)
            page.wait_for_timeout(150)
            zoomed = page.evaluate("document.querySelector('#zoom-level').textContent")
            stroke_from(700, 500, 40, 30)

            page.click("#btn-hand")                           # 3. pan, then draw again
            drag(screen_of(700, 500), -120, -90)
            page.click("#btn-hand")
            stroke_from(640, 460, 30, 25)

            page.evaluate("ArtLog.flush()")                   # local-first queue, push it now
            page.wait_for_timeout(1500)
            browser.close()

        self.assertEqual(errors, [], "JS errors on the page")
        self.assertEqual(zoomed, "800%")                      # 12 wheel ticks hit MAX_ZOOM

        sid = (self._ids() - before).pop()
        strokes = self._get(f"/api/sessions/{sid}/strokes")
        self.assertEqual(len(strokes), 3, strokes)

        # The whole point: identical canvas coordinates, whatever the view was.
        for stroke, (want_x, want_y) in zip(strokes, [(200, 200), (700, 500), (640, 460)]):
            x, y = stroke["points"][0][0], stroke["points"][0][1]
            self.assertAlmostEqual(x, want_x, delta=6, msg=f"{stroke['stroke_id']} x at zoom {stroke.get('zoom')}")
            self.assertAlmostEqual(y, want_y, delta=6, msg=f"{stroke['stroke_id']} y at zoom {stroke.get('zoom')}")

        # …while the zoom the child was working at is still recorded
        self.assertEqual(strokes[0]["zoom"], 1.0)
        self.assertEqual(strokes[1]["zoom"], 8.0)
        self.assertEqual(strokes[2]["zoom"], 8.0)

        # a mouse reports a constant 0.5 pressure and no tilt; that is not a
        # measurement, so it must reach the log as null rather than as a number
        for stroke in strokes:
            self.assertEqual(stroke["pointer"], "mouse")
            self.assertFalse(stroke["pressure_supported"])
            self.assertFalse(stroke["tilt_supported"])
            for pt in stroke["points"]:
                self.assertIsNone(pt[3], "pressure was fabricated")
                self.assertIsNone(pt[4], "tilt was fabricated")

        events = self._get(f"/api/sessions/{sid}")["events"]
        kinds = [e["type"] for e in events]
        # every stroke is bracketed, and a zoom gesture closes before the stroke
        # it was made for — pen-down is when the child started, not when they let go
        self.assertEqual([k for k in kinds if k in ("STROKE_START", "STROKE_END", "ZOOM", "PAN")],
                         ["STROKE_START", "STROKE_END", "ZOOM",
                          "STROKE_START", "STROKE_END", "PAN",
                          "STROKE_START", "STROKE_END"])
        starts = [e for e in events if e["type"] == "STROKE_START"]
        ends = [e for e in events if e["type"] == "STROKE_END"]
        self.assertEqual([e["payload"]["stroke_id"] for e in starts],
                         [e["payload"]["stroke_id"] for e in ends])
        zoom_ev = next(e for e in events if e["type"] == "ZOOM")["payload"]
        self.assertEqual((zoom_ev["from"], zoom_ev["to"], zoom_ev["source"]), (1.0, 8.0, "wheel"))
        self.assertGreater(len(zoom_ev["steps"]), 1)          # the raw trace, not just the endpoint
        pan_ev = next(e for e in events if e["type"] == "PAN")["payload"]
        self.assertNotEqual(pan_ev["from"], pan_ev["to"])
        self.assertGreater(len(pan_ev["points"]), 1)


    def test_a_zoomed_session_with_an_undo_still_reconstructs(self):
        """End to end in a real browser: the QC threshold meets real canvas output.

        Everything before this was PIL drawing against PIL. Here the artwork is
        rasterised by Chrome and the replay by Pillow, with a zoom and an undo in
        between — which is exactly the case the log has to survive.
        """
        errors, before = [], self._ids()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("pageerror", lambda e: errors.append(str(e)))
            self._start(page, "undo under zoom")
            screen_of, drag, stroke_from = self._canvas_tools(page)

            for i in range(3):
                stroke_from(180 + i * 130, 200, 150, 220)
            page.mouse.move(*screen_of(500, 350))
            for _ in range(6):
                page.mouse.wheel(0, -120)
            page.wait_for_timeout(150)
            stroke_from(500, 350, 60, 40)                     # drawn zoomed in…
            page.click("#btn-undo")                           # …and taken straight back off
            page.click("#btn-zoom-reset")

            # QC rejects anything under MIN_DURATION_MS as a misfire, and it is
            # right to: a robot that finishes in three seconds is not a session.
            page.wait_for_timeout(5200)
            page.click("#btn-submit")
            page.wait_for_selector("#view-result:not(.hidden)")
            page.click("#btn-skip-revise")
            page.wait_for_selector("#view-final:not(.hidden)", timeout=20000)
            browser.close()

        self.assertEqual(errors, [], "JS errors on the page")
        sid = (self._ids() - before).pop()
        meta = self._get(f"/api/sessions/{sid}")
        qc = meta["qc"]

        # four strokes logged for ever, three of them on the artwork
        self.assertEqual(qc["counts"]["strokes"], 4)
        self.assertEqual(qc["counts"]["strokes_visible"], 3)
        self.assertEqual(qc["counts"]["strokes_removed"], 1)
        self.assertTrue(qc["ok"], qc["failed"])

        undo = next(e for e in meta["events"] if e["type"] == "UNDO")["payload"]
        self.assertEqual(undo["removed"], ["s00004"])
        self.assertEqual(undo["visible_n"], 3)

        # and the reconstruction really does match what Chrome drew
        detail = next(c for c in qc["checks"] if c["name"] == "replay_matches_final")["detail"]
        self.assertLess(detail["rel"], 0.30)
        self.assertEqual(next(c for c in qc["checks"] if c["name"] == "log_streams_agree")["detail"]["status"], "ok")


    def test_looking_at_the_reference_is_recorded_as_behaviour(self):
        """Look → draw → check → correct only exists if the reference records it."""
        errors, before = [], self._ids()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1500, "height": 1100})
            page.on("pageerror", lambda e: errors.append(str(e)))
            self._start(page, "reference", family="博物馆修复师")
            screen_of, drag, stroke_from = self._canvas_tools(page)

            # M1's reference is `mode: always`, so the task presents it at the
            # start — clicking the toggle here would close it, not open it
            page.wait_for_selector("#ref-viewport", state="visible")
            box = page.eval_on_selector("#ref-viewport",
                                        "e=>{const b=e.getBoundingClientRect();return [b.left,b.top,b.width,b.height]}")
            centre = (box[0] + box[2] / 2, box[1] + box[3] / 2)
            page.mouse.move(*centre)                           # attention: reference
            for _ in range(6):
                page.mouse.wheel(0, -120)                      # zoom into the reference
            page.wait_for_timeout(120)
            zoom = page.eval_on_selector("#ref-zoom", "e=>e.textContent")
            drag(centre, -40, -30)                             # pan it
            stroke_from(300, 300, 80, 120)                     # attention: canvas
            page.wait_for_timeout(200)
            page.click("#btn-ref-toggle")                      # and close it again
            page.evaluate("ArtLog.flush()")
            page.wait_for_timeout(1500)
            browser.close()

        self.assertEqual(errors, [], "JS errors on the page")
        sid = (self._ids() - before).pop()
        events = self._get(f"/api/sessions/{sid}")["events"]
        kinds = [e["type"] for e in events]
        for want in ("REFERENCE_SHOW", "REFERENCE_OPEN", "REFERENCE_ZOOM",
                     "REFERENCE_PAN", "REFERENCE_FOCUS", "CANVAS_FOCUS", "REFERENCE_CLOSE"):
            self.assertIn(want, kinds, want)

        self.assertNotEqual(zoom, "100%")
        zoomed = next(e for e in events if e["type"] == "REFERENCE_ZOOM")["payload"]
        self.assertGreater(zoomed["to"], zoomed["from"])
        closed = next(e for e in events if e["type"] == "REFERENCE_CLOSE")["payload"]
        # how long they looked, not merely that they did
        self.assertGreater(closed["view_duration_ms"], 0)
        self.assertTrue(closed["reference_id"])
        shown = next(e for e in events if e["type"] == "REFERENCE_SHOW")["payload"]
        self.assertTrue(shown["placeholder"], "a placeholder stimulus must say so")
        # the switch back to the canvas is what makes look→draw→check countable
        self.assertLess(kinds.index("REFERENCE_FOCUS"), kinds.index("CANVAS_FOCUS"))


if __name__ == "__main__":
    unittest.main()
