"""没网时点「画好了」：画存在设备上，网回来自动补交（用户 2026-10-05：带回家画，离线了有些东西不显示就好）。

守三件事：
1. 服务器收到 `deferred: true` 的交卷：照常打分，不生成反馈，直接结束，记成「无反馈、未修改」并打上 offline_submit。
2. 真浏览器：断网开一张、画几笔、点「画好了」→ 没有报错、回到任务页、交卷排进发件箱；
   插回网线 → 服务器上多出这张画，状态 done、offline_submit，每一笔都在。
3. 没网时 body 带 .offline，要服务器的区块（大家的画廊等）不显示。

Run:  python3 -m unittest -v
"""
import base64
import io
import json
import unittest
import urllib.request

from .env import TMP as _TMP, ADMIN  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest.main import app  # noqa: E402
from . import test_offline as _off  # noqa: E402  （不把父类拉进本模块的命名空间，免得它的用例在这里再跑一遍）


def _data_url():
    img = Image.new("RGB", (320, 220), "white")
    ImageDraw.Draw(img).ellipse((40, 40, 220, 180), fill=(150, 190, 235), outline="black", width=4)
    buf = io.BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class DeferredSubmitAPI(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def test_a_deferred_submit_scores_but_gives_no_feedback_and_ends_the_session(self):
        r = self.c.post("/api/sessions", json={"quest_id": "imagine_animal", "intent": {"emotion": "开心", "text": "猫"},
                                               "participant": {"anon_id": "anon-offline-1"}})
        sid = r.json()["session_id"]
        r = self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(), "elapsed_ms": 8000, "phase": "before", "deferred": True})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["deferred"]); self.assertIsNone(body["feedback"])
        self.assertEqual(len(body["scores"]["dims"]), 9, "评分照常")
        s = body["session"]
        self.assertEqual(s["status"], "done"); self.assertFalse(s["revised"]); self.assertTrue(s["offline_submit"])
        self.assertIsNone(s.get("feedback"))
        self.assertEqual(s["after"]["file"], "final.png")
        types = [e["type"] for e in s["events"]]
        self.assertIn("FEEDBACK_SKIPPED", types); self.assertIn("SESSION_END", types)
        # 结束了就不能再交、也不能再 finalize 出第二份
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/submit", json={"image": _data_url(), "elapsed_ms": 9000, "phase": "before"}).status_code, 409)
        self.assertIn(sid, [x["session_id"] for x in self.c.get("/api/sessions?anon_id=anon-offline-1").json()], "画廊里有它")


@unittest.skipUnless(_off.sync_playwright and _off._chrome_available(), "needs playwright + Chrome")
class SubmitWithNoNetwork(_off.DrawingWithNoNetwork):
    # 父类自己的用例不在这里再跑一遍
    test_a_drawing_made_offline_arrives_complete_when_the_network_comes_back = None
    test_a_cold_launch_with_no_network_still_reaches_the_canvas = None
    test_changing_the_stylesheet_shows_up_on_the_very_next_open = None

    def test_done_while_offline_is_sent_when_the_network_returns(self):
        before = {r["session_id"] for r in self._get("/api/sessions")}
        errors = []
        with _off.sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            context = browser.new_context(viewport={"width": 1180, "height": 820}, has_touch=True)
            page = context.new_page(); page.set_default_timeout(15000)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: (errors.append("dialog: " + d.message), d.accept()))
            page.add_init_script("localStorage.setItem('artquest.tour/2','1'); localStorage.setItem('artquest.acct_prompted','1')")
            page.goto(self.base, wait_until="networkidle")
            page.wait_for_function("async () => (await ArtLog.countTickets()) > 0")
            page.wait_for_selector("#view-world:not(.hidden)"); page.click("#btn-enter-world")
            page.wait_for_selector("#quest-grid .quest-card"); page.click("#quest-grid .quest-card"); page.click("#btn-today")
            page.wait_for_timeout(400); page.click("#emotion-chips button")

            context.set_offline(True)                                   # ← 拔网线
            page.evaluate("() => window.dispatchEvent(new Event('offline'))")
            page.click("#btn-start-draw"); page.wait_for_selector("#view-draw:not(.hidden)"); page.wait_for_timeout(500)
            self.assertTrue(page.evaluate("() => document.body.classList.contains('offline')"), "没网 body 要带 .offline")
            box = page.locator("#canvas").bounding_box()
            for k in range(4):
                x, y = box["x"] + box["width"] * (0.2 + k * 0.15), box["y"] + box["height"] * 0.3
                page.mouse.move(x, y); page.mouse.down()
                for i in range(1, 10): page.mouse.move(x + i * 6, y + i * 15)
                page.mouse.up()
            page.wait_for_timeout(600)
            page.click("#btn-submit")                                   # 「画好了」
            page.wait_for_selector("#view-quest:not(.hidden)", timeout=10000)
            kinds = page.evaluate("async () => await ArtLog.outboxCount()")
            self.assertGreaterEqual(kinds, 2, "发件箱里该有「建 session」和「交卷」两条")

            context.set_offline(False)                                  # ← 插回去
            page.evaluate("() => window.dispatchEvent(new Event('online'))")
            page.wait_for_function("async () => (await ArtLog.outboxCount()) === 0", timeout=25000)
            page.wait_for_timeout(1500)
            self.assertFalse(page.evaluate("() => document.body.classList.contains('offline')"))
            browser.close()

        self.assertEqual(errors, [], "页面上有报错或弹窗")
        new = [r for r in self._get("/api/sessions") if r["session_id"] not in before]
        self.assertEqual(len(new), 1, f"应该正好多出一张画，实际 {len(new)}")
        meta = self._get(f"/api/sessions/{new[0]['session_id']}")
        self.assertEqual(meta["status"], "done"); self.assertTrue(meta.get("offline_submit"))
        self.assertIsNone(meta.get("feedback"))
        self.assertEqual(meta["id_source"], "ticket")
        strokes = self._get(f"/api/sessions/{new[0]['session_id']}/strokes")
        self.assertEqual(len(strokes), 4, f"离线画了 4 笔，服务器上只有 {len(strokes)} 笔")
