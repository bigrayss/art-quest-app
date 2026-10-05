"""离线创作的地基：预发的票。

孩子在没有网的时候开始画，那一刻不能向服务器要 `session_id`。朴素的做法是
让客户端自己发一个——但那会**一次性毁掉三样东西**：

  1. **id 的可信性**。`session_id` 是后面每张表的外键，客户端发的 id 谁都能编。
  2. **条件冻结**。孩子究竟跑在哪条实验臂上，必须由服务端说了算；让离线的
     客户端自己算一遍，等于把实验设计交给设备上那份可能过期的配置。
  3. **重放时的可分辨性**。`/log` 对不认识的 session 返回 404，而 `log.js` 把
     4xx 当成「服务器拒了这一行」→ 隔离。分不清「还没建」和「不存在」的话，
     离线画的每一笔都会被静默扔掉——画了等于没画。

票据把服务端的决定**提前**而不是拿掉：联网时一次发几张，每张带着 id 和冻好的
条件，目录当场占住。这个文件盯的就是那三条。
"""
import json
import pathlib
import unittest

from .env import TMP as _TMP, ADMIN  # noqa: F401  (offline backends, throwaway data dir)

from fastapi.testclient import TestClient  # noqa: E402

from artquest.main import app  # noqa: E402
from artquest.storage import LIFECYCLE  # noqa: E402


class Tickets(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        self.quest = self.c.get("/api/quests").json()[0]["id"]

    def _ticket(self, **kw):
        r = self.c.post("/api/tickets", json={"n": 1, **kw})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["tickets"][0]

    def _start(self, sid="", quest=None):
        body = {"quest_id": quest or self.quest, "intent": {"emotion": "开心", "text": ""}}
        if sid:
            body["session_id"] = sid
        return self.c.post("/api/sessions", json=body)

    # -- 1. id 由服务端发 ---------------------------------------------------
    def test_a_ticket_carries_a_server_made_id_and_a_frozen_condition(self):
        t = self._ticket()
        self.assertTrue(t["session_id"])
        self.assertIn("feedback_source", t["condition"], "票上必须带着冻好的条件")
        self.assertTrue(t["issued_at"])

    def test_issued_before_recording_so_lifecycle_still_only_goes_forward(self):
        self.assertEqual(LIFECYCLE[0], "issued")
        self.assertLess(LIFECYCLE.index("issued"), LIFECYCLE.index("recording"))

    def test_an_id_that_was_never_issued_is_refused(self):
        """这条是防后门的：认了编造的票号，就等于客户端可以自己发 id。"""
        r = self._start(sid="deadbeef0000")
        self.assertEqual(r.status_code, 404, r.text)

    # -- 2. 条件以票上的为准 -------------------------------------------------
    def test_the_condition_on_the_ticket_wins_over_a_later_resolve(self):
        """票是联网时发的，孩子离线跑的就是票上那条臂。

        重放时 study.json 可能已经被改过；再 resolve 一次会得到另一个答案，
        那样记下来的就不是孩子实际经历的东西。
        """
        t = self._ticket()
        frozen = dict(t["condition"])
        frozen["zoom_allowed"] = not frozen.get("zoom_allowed", True)
        # 直接改票上的条件，模拟「发票之后服务端配置变了」
        import json
        from artquest.config import SESSIONS_DIR
        f = SESSIONS_DIR / t["session_id"] / "session.json"
        meta = json.loads(f.read_text())
        meta["condition"] = frozen
        f.write_text(json.dumps(meta, ensure_ascii=False))

        r = self._start(sid=t["session_id"])
        self.assertEqual(r.status_code, 201, r.text)
        got = r.json()["session"]["condition"]
        self.assertEqual(got["zoom_allowed"], frozen["zoom_allowed"],
                         "花票时又重新算了一遍条件，孩子实际经历的那条臂丢了")

    # -- 3. 重放安全 ---------------------------------------------------------
    def test_spending_the_same_ticket_twice_never_wipes_what_is_already_there(self):
        """离线队列会重发创建。重发绝不能把一个已经有笔画的 session 抹回空的。"""
        t = self._ticket()
        first = self._start(sid=t["session_id"])
        self.assertEqual(first.status_code, 201, first.text)
        sid = first.json()["session_id"]

        self.c.post(f"/api/sessions/{sid}/log", json={"events": [], "pending": 1, "strokes": [
            {"seq": 1, "stroke_id": "s00001", "phase": "before", "op": "draw", "t0_ms": 0,
             "tool": "pencil", "color": "#222222", "size": 4, "opacity": 1,
             "points": [[10, 10, 0, None, None, None], [40, 40, 50, None, None, None]]}]})
        before = self.c.get(f"/api/sessions/{sid}/strokes").json()
        self.assertEqual(len(before), 1)

        again = self._start(sid=t["session_id"])
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json().get("replayed"), "重放没有被认出来")
        after = self.c.get(f"/api/sessions/{sid}/strokes").json()
        self.assertEqual(after, before, "重发创建把已经收上来的笔画抹掉了")

    # -- 没花掉的票不是作品 --------------------------------------------------
    def test_an_unspent_ticket_never_shows_up_as_a_drawing(self):
        """它没有画、没有时间、没有任务——出现在画廊里就是一个空壳。"""
        t = self._ticket(participant={"anon_id": "anon-ticket-test"})
        rows = self.c.get("/api/sessions", params={"anon_id": "anon-ticket-test"}).json()
        self.assertEqual([r for r in rows if r["session_id"] == t["session_id"]], [])
        # 花掉、画了一笔之后就该出现了（一笔没画的空局也不算作品，用户 2026-10-05）
        self.c.post("/api/sessions", json={
            "quest_id": self.quest, "intent": {"emotion": "开心", "text": ""},
            "session_id": t["session_id"], "participant": {"anon_id": "anon-ticket-test"}})
        self.c.post(f"/api/sessions/{t['session_id']}/log", json={"events": [], "strokes": [{"seq": 1, "stroke_id": "s00001", "phase": "before", "t_start_ms": 900, "tool": "pencil", "color": "#222222", "size": 4, "opacity": 1.0, "points": [[100, 100, 0, None, None, None], [160, 140, 90, None, None, None]]}]})
        rows = self.c.get("/api/sessions", params={"anon_id": "anon-ticket-test"}).json()
        self.assertEqual(len([r for r in rows if r["session_id"] == t["session_id"]]), 1)


# -- 真浏览器：断网画一张，连回来它必须在 ---------------------------------
import socket
import threading
import time
import urllib.request

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


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
class DrawingWithNoNetwork(unittest.TestCase):
    """断网开一张新的、画完、再连回来——服务器上要有这张画和它的每一笔。

    这条盯的是整条链路里最容易**静默丢数据**的那一段：离线时 `/log` 会对一个
    还没建出来的 session 返回 404，而 `log.js` 把 4xx 当成「服务器拒了这一行」
    并隔离掉。没有发件箱的顺序约束，孩子离线画的每一笔都会那样消失——
    界面上一切正常，盘上什么都没有。
    """

    @classmethod
    def setUpClass(cls):
        import uvicorn

        from artquest.main import app
        s = socket.socket(); s.bind(("127.0.0.1", 0)); cls.port = s.getsockname()[1]; s.close()
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

    def test_a_drawing_made_offline_arrives_complete_when_the_network_comes_back(self):
        before = {r["session_id"] for r in self._get("/api/sessions")}
        errors = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            context = browser.new_context(viewport={"width": 1180, "height": 820}, has_touch=True)
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: (errors.append("dialog: " + d.message), d.accept()))
            page.add_init_script("localStorage.setItem('artquest.tour/2','1'); localStorage.setItem('artquest.acct_prompted','1')")
            page.goto(self.base, wait_until="networkidle")
            # 票是**联网时**领的：离线要用的 id 和条件都已经由服务端定好
            page.wait_for_function("async () => (await ArtLog.countTickets()) > 0")

            page.wait_for_selector("#view-world:not(.hidden)")
            page.click("#btn-enter-world")
            page.wait_for_selector("#quest-grid .quest-card")
            page.click("#quest-grid .quest-card")
            page.click("#btn-today")
            page.wait_for_timeout(400)
            page.click("#emotion-chips button")

            held = page.evaluate("async () => await ArtLog.countTickets()")
            context.set_offline(True)                       # ← 拔网线

            page.click("#btn-start-draw")
            page.wait_for_selector("#view-draw:not(.hidden)")
            page.wait_for_timeout(600)
            self.assertEqual(page.evaluate("async () => await ArtLog.countTickets()"), held - 1,
                             "离线开工没有花掉一张票")
            self.assertEqual(page.evaluate("async () => await ArtLog.outboxCount()"), 1,
                             "「建 session」没有进发件箱")

            box = page.locator("#canvas").bounding_box()
            for k in range(5):
                x, y = box["x"] + box["width"] * (0.2 + k * 0.12), box["y"] + box["height"] * 0.3
                page.mouse.move(x, y)
                page.mouse.down()
                for i in range(1, 10):
                    page.mouse.move(x + i * 6, y + i * 15)
                page.mouse.up()
            page.wait_for_timeout(800)
            self.assertGreater(page.evaluate("async () => await ArtLog.pending()"), 0,
                               "离线画的东西没有排在设备上")

            context.set_offline(False)                      # ← 插回去
            page.evaluate("() => window.dispatchEvent(new Event('online'))")
            page.wait_for_function("async () => (await ArtLog.outboxCount()) === 0", timeout=20000)
            page.evaluate("ArtLog.flush()")
            page.wait_for_timeout(2500)
            browser.close()

        self.assertEqual(errors, [], "页面上有报错或弹窗")
        new = {r["session_id"] for r in self._get("/api/sessions")} - before
        self.assertEqual(len(new), 1, f"应该正好多出一张画，实际 {len(new)}")
        sid = new.pop()
        meta = self._get(f"/api/sessions/{sid}")
        self.assertEqual(meta["id_source"], "ticket", "离线开的 session 应该是花票来的")
        strokes = self._get(f"/api/sessions/{sid}/strokes")
        self.assertEqual(len(strokes), 5, f"离线画了 5 笔，服务器上只有 {len(strokes)} 笔")
        self.assertEqual([s["seq"] for s in strokes], [1, 2, 3, 4, 5], "笔画的顺序乱了")

    def test_a_cold_launch_with_no_network_still_reaches_the_canvas(self):
        """关掉 app、断网、点图标重开——要能一路走到画画。

        这是「装到主屏」真正兑现的那一刻，也是最容易只兑现一半的地方：

        - 第一次打开页面时 **SW 还没接管**，`/api/config`、`/api/quests` 那几个
          请求根本不经过它。不在装的时候主动抓一份，第一次断网冷启动就只能指望
          浏览器自己的 HTTP 缓存——撞不到就是地图空白、连任务都选不了。
        - 离线开工时 `ArtLog.start()` 还没跑过，IndexedDB 还没打开。票的读取
          要是直接读 `db`，「有 3 张票」会被读成「一张都没有」，孩子看到的是
          「这台设备上没有备用的创作名额了」——明明有。

        跑在 127.0.0.1 上：和 HTTPS 一样算 secure context，SW 会注册。
        真机上这条路要 HTTPS（Tailscale 或域名），那是部署问题，不是代码问题。
        """
        notes = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            context = browser.new_context(viewport={"width": 1180, "height": 820}, has_touch=True)
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on("pageerror", lambda e: notes.append("JS: " + str(e)))
            page.on("dialog", lambda d: (notes.append("dialog: " + d.message), d.accept()))
            page.add_init_script("localStorage.setItem('artquest.tour/2','1'); localStorage.setItem('artquest.acct_prompted','1')")

            # 联网开一次：注册 SW、存外壳、领票
            page.goto(self.base, wait_until="networkidle")
            page.wait_for_function(
                "async () => { const r = await navigator.serviceWorker.getRegistration();"
                " return !!(r && r.active); }")
            page.wait_for_function("async () => (await ArtLog.countTickets()) > 0")
            cached = page.evaluate("""async () => {
                const names = await caches.keys(), out = [];
                for (const n of names) {
                    const c = await caches.open(n);
                    (await c.keys()).forEach(r => out.push(new URL(r.url).pathname));
                }
                return out;
            }""")
            for must in ("/api/v1/config", "/api/v1/quests", "/api/v1/families"):
                self.assertIn(must, cached, f"{must} 没在装 SW 的时候抓下来，冷启动会是空白的")
            page.close()

            # 关掉、断网、开一个全新的页面
            context.set_offline(True)
            cold = context.new_page()
            cold.set_default_timeout(15000)
            cold.on("pageerror", lambda e: notes.append("JS: " + str(e)))
            cold.on("dialog", lambda d: (notes.append("dialog: " + d.message), d.accept()))
            cold.goto(self.base, wait_until="domcontentloaded")
            self.assertIn("彩绘冒险", cold.title(), "断网点图标打不开")

            cold.wait_for_selector("#view-world:not(.hidden)")
            cold.click("#btn-enter-world")
            cold.wait_for_selector("#quest-grid .quest-card")
            self.assertGreater(cold.eval_on_selector_all("#quest-grid .quest-card", "e => e.length"), 0,
                               "断网之后地图是空的")
            cold.click("#quest-grid .quest-card")
            cold.click("#btn-today")
            cold.wait_for_timeout(400)
            cold.click("#emotion-chips button")
            cold.click("#btn-start-draw")
            cold.wait_for_selector("#view-draw:not(.hidden)")   # ← 走到画布就算兑现
            browser.close()

        self.assertEqual(notes, [], "冷启动路上有报错或弹窗")

    def test_changing_the_stylesheet_shows_up_on_the_very_next_open(self):
        """离线能开，不能变成「永远开的是旧的」。

        真机上栽过一次：改完之后 iPad 上是**新的 HTML 配旧的 CSS 和 JS**——
        收起按钮画出来了，却没有样式也没有事件，看着就是坏的。两层缓存叠在一起：

        1. SW 用的是 stale-while-revalidate：先给旧的、后台换新的。HTML/CSS/JS
           各自独立过期，于是外壳会处在**半新半旧**的状态。
        2. `StaticFiles` 一个 `Cache-Control` 都不发，浏览器就按启发式自己存，
           连 SW 的 `fetch` 都拿不到新的。

        现在：服务端发 `no-cache`（每次回来问一句，没变就是个 304），
        SW 网络优先且 `cache: "reload"` 绕开浏览器那层。这条测试盯着别退回去。
        """
        import time as _t

        import re as _re

        css = pathlib.Path(__file__).resolve().parent.parent / "static" / "style.css"
        original = css.read_text()
        # 盯的是「改了样式表能不能立刻看到」，不是某个具体数值——
        # 所以按变量名找，别把栏宽的字面量写死在这儿（写死过一次，
        # 栏宽一调这条就自己红了）。
        m = _re.search(r"(\.app \{ --rail-w: )([\d.]+)(rem; \})", original)
        self.assertIsNotNone(m, "样式表里找不到 --rail-w，这条测试要跟着改")
        bumped = original.replace(m.group(0), f"{m.group(1)}{float(m.group(2)) + 5}{m.group(3)}")
        self.assertNotEqual(bumped, original)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                context = browser.new_context(viewport={"width": 1180, "height": 820})
                page = context.new_page()
                page.set_default_timeout(15000)
                page.add_init_script("localStorage.setItem('artquest.tour/2','1'); localStorage.setItem('artquest.acct_prompted','1')")
                page.goto(self.base, wait_until="networkidle")
                page.wait_for_function(
                    "async () => { const r = await navigator.serviceWorker.getRegistration();"
                    " return !!(r && r.active); }")
                page.wait_for_timeout(1200)
                before = page.evaluate("() => getComputedStyle(document.querySelector('.tabbar')).width")

                css.write_text(bumped)
                _t.sleep(0.4)
                page.reload(wait_until="networkidle")
                # 改了样式表，外壳的哈希就变了（`main.shell_version()`），于是 SW 装上
                # 新版本、接手、页面**自己再重载一次**——正是这条测试想要的效果，
                # 但取值要等它落定，不然会撞在导航中间（execution context destroyed）。
                page.wait_for_timeout(2500)
                after = None
                for _ in range(4):
                    try:
                        after = page.evaluate(
                            "() => getComputedStyle(document.querySelector('.tabbar')).width")
                        break
                    except Exception:
                        page.wait_for_timeout(900)
                browser.close()
        finally:
            css.write_text(original)

        self.assertNotEqual(after, before,
                            f"改了样式表，下一次打开拿到的还是旧的（{before}）——"
                            "外壳会半新半旧")


if __name__ == "__main__":
    unittest.main()
