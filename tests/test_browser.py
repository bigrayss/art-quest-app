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

from .env import ADMIN, TMP as _TMP  # noqa: F401  (offline backends, throwaway data dir)

try:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
    PWTimeout = Exception


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
        return json.load(urllib.request.urlopen(urllib.request.Request(self.base + path, headers=ADMIN)))

    def _ids(self):
        return {r["session_id"] for r in self._get("/api/sessions")}

    def test_the_tour_points_at_real_buttons_and_only_shows_once(self):
        """说明只说一次，而且是**指着按钮**说的。

        每一屏上原来都挂着一行小字说明；四处小字加起来就是一层灰，对第二次打开的
        孩子毫无用处。现在它们收成第一次进来的聚光灯导览：暗掉全屏，把正在说的那颗
        按钮留在亮处，旁边一句话。看过就不再出现（「我的」里可以再看一遍）。
        """
        if type(self) is not ZoomKeepsStrokesInCanvasSpace:
            self.skipTest("基类跑一次就够")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 820, "height": 1180})
            page.set_default_timeout(15000)
            page.goto(self.base)
            # 第一次打开先是门口（起名字 / 先随便看看），导览在门口之后
            page.click("#btn-welcome-skip")
            page.wait_for_selector("#tour:not(.hidden)")

            seen = []
            for _ in range(6):
                page.wait_for_timeout(400)
                box = page.evaluate("""() => {
                  const h = document.querySelector('#tour-hole').getBoundingClientRect();
                  const t = document.querySelector('#tour-tip').getBoundingClientRect();
                  return {hole: [h.left, h.top, h.width, h.height],
                          tip: [t.left, t.top, t.right, t.bottom],
                          text: document.querySelector('#tour-text').textContent};
                }""")
                # 洞要真的罩在一个元素上，卡片要整个留在屏幕里
                self.assertGreater(box["hole"][2], 8, "聚光灯没有罩住任何东西")
                self.assertGreater(box["hole"][3], 8)
                self.assertGreaterEqual(box["tip"][0], 0)
                self.assertLessEqual(box["tip"][2], 820 + 1)
                self.assertLessEqual(box["tip"][3], 1180 + 1)
                seen.append(box["text"])
                page.click("#btn-tour-next")
            self.assertEqual(len(set(seen)), 6, "六步该说六件不同的事")
            page.wait_for_function("() => document.querySelector('#tour').classList.contains('hidden')")

            page.reload()
            page.wait_for_selector("#view-world:not(.hidden), #quest-grid .quest-card")
            self.assertTrue(page.is_hidden("#tour"), "看过一次就不该再拦路")

            page.click(".tab[data-tab='me']")
            page.click("#btn-guide-again")
            page.wait_for_selector("#tour:not(.hidden)")
            browser.close()

    def test_the_first_launch_is_a_front_door_not_a_flash_of_the_map(self):
        """第一次打开：一张安静的封面，然后是门口——不是空地图闪一下、满地图闪一下再跳到封面。

        HTML 里唯一不带 hidden 的视图是门口，所以 JS 还在问服务器的那一两秒屏幕上就是它，
        没有顶栏也没有 tab。门口只问一件事（名字 + 四位暗号），答了或者「先随便看看」都进世界，
        而且只问这一次：同一台设备再打开直接是封面。登录着的设备根本不会到门口。
        """
        if type(self) is not ZoomKeepsStrokesInCanvasSpace:
            self.skipTest("基类跑一次就够")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            ctx = browser.new_context(viewport={"width": 820, "height": 1180})
            page = ctx.new_page()
            page.set_default_timeout(15000)
            # 一提交就看：门口已经在，地图藏着，导航不露（init 跑完之前之后都该如此）
            page.goto(self.base, wait_until="commit")
            self.assertTrue(page.is_visible("#view-welcome"), "启动期间该是门口")
            self.assertTrue(page.is_hidden("#view-quest"), "启动期间不该露出地图")
            self.assertTrue(page.is_hidden("#tabbar")); self.assertTrue(page.is_hidden(".appbar"))
            page.wait_for_function("() => !document.body.classList.contains('booting')")
            self.assertTrue(page.is_visible("#btn-welcome-register"))
            self.assertTrue(page.is_hidden("#tour"), "门口上不该同时压着导览")

            # 起个名字 → 封面 + 导览；「我的」里是登录态
            page.click("#btn-welcome-register")
            page.fill("#acct-name-input", "门口人"); page.fill("#acct-pin-input", "1357")
            page.click("#btn-acct-go")
            page.wait_for_selector("#view-world:not(.hidden)")
            page.wait_for_selector("#tour:not(.hidden)")
            self.assertTrue(page.is_hidden("#view-welcome"))
            page.click("#btn-tour-skip")
            page.click(".tab[data-tab='me']")
            page.wait_for_selector("#acct-in:not(.hidden)")
            self.assertEqual(page.inner_text("#acct-name"), "门口人")

            # 同一台设备再开：不再问，直接封面
            again = ctx.new_page(); again.set_default_timeout(15000)
            again.goto(self.base)
            again.wait_for_function("() => !document.body.classList.contains('booting')")
            self.assertTrue(again.is_hidden("#view-welcome")); self.assertTrue(again.is_visible("#view-world"))
            self.assertTrue(again.is_hidden("#tour"))

            # 没名字也能进：「先随便看看」→ 封面 + 导览
            fresh = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
            fresh.set_default_timeout(15000)
            fresh.goto(self.base); fresh.click("#btn-welcome-skip")
            fresh.wait_for_selector("#view-world:not(.hidden)"); fresh.wait_for_selector("#tour:not(.hidden)")
            browser.close()

    def test_an_empty_collection_still_hangs_a_wall(self):
        """一张画都没有的时候，画廊里挂的是一面**空墙**，不是什么都没有。

        整块区域消失会让人以为这一屏坏了，而它只是还在等第一张画——
        大家那面墙早就是这么做的，自己的那面照抄同一个做法。
        """
        if type(self) is not ZoomKeepsStrokesInCanvasSpace:
            self.skipTest("基类跑一次就够")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 820, "height": 1180})
            page.set_default_timeout(15000)
            # 一个没人用过的设备代号：这条测的就是「一张画都没有」那一刻
            page.add_init_script("""
              localStorage.setItem('artquest.tour/2', '1'); localStorage.setItem('artquest.acct_prompted', '1');
              localStorage.setItem('artquest.anon_id', 'anon-empty-dex');
              sessionStorage.setItem('artquest.entered', '1');
            """)
            page.goto(self.base)
            # #view-quest 初始就没有 hidden 类，所以等的是关卡真的渲染出来；
            # init 收尾时还会自己 show 一次，撞上了就再点一下
            page.wait_for_selector("#quest-grid > *")
            for _ in range(4):
                page.click(".tab[data-tab='dex']")
                try:
                    page.wait_for_selector("#view-dex:not(.hidden)", timeout=3000)
                    break
                except PWTimeout:
                    page.wait_for_timeout(300)

            page.wait_for_selector("#collection-wrap:not(.hidden)")
            self.assertTrue(page.is_visible("#dex-empty"), "空墙上该写着一句话")
            self.assertEqual(page.locator(".dex-card").count(), 0)
            # 「0/75 种」是把「还没开始」写成一张成绩单，空墙上不挂
            self.assertEqual(page.inner_text("#dex-progress").strip(), "")
            browser.close()

    def test_the_badge_wall_never_says_how_many_are_left(self):
        """墙上只有点亮过的，外加一张「还有别的」。

        报个数（「还有 31 枚」）听着无害，其实把发现变回了进度条：
        孩子会开始数，而不是继续画。所以墙上**任何地方都不出现总数**。
        """
        if type(self) is not ZoomKeepsStrokesInCanvasSpace:
            self.skipTest("基类跑一次就够")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 820, "height": 1180})
            page.set_default_timeout(15000)
            page.add_init_script("""
              localStorage.setItem('artquest.tour/2', '1'); localStorage.setItem('artquest.acct_prompted', '1');
              localStorage.setItem('artquest.anon_id', 'anon-badge-wall');
              localStorage.setItem('artquest.buddy_name', '阿布');
              sessionStorage.setItem('artquest.entered', '1');
            """)
            page.goto(self.base)
            page.wait_for_selector("#quest-grid > *")
            for _ in range(4):
                page.click(".tab[data-tab='buddy']")
                try:
                    page.wait_for_selector("#view-buddy:not(.hidden)", timeout=3000)
                    break
                except PWTimeout:
                    page.wait_for_timeout(300)
            # 这面墙要等两个请求（自己的 session 列表 + 全服稀有度）才画得出来。
            # 满负载跑整套测试的时候它们会慢下来，所以这里给得比别处宽。
            page.wait_for_selector("#badge-wall .badge", timeout=30000)

            wall = page.inner_text("#badge-wall")
            self.assertIn("更多等你发现", wall, "墙尾该留一枚「?」")
            self.assertNotIn("还有 ", wall)
            self.assertNotIn("全部 ", wall)
            # 一枚灰的都不该有：没点亮的根本不展示
            self.assertEqual(page.locator("#badge-wall .badge:not(.on):not(.mystery)").count(), 0)
            # 一打开就有的那枚（「加入家庭」）不经服务器，它得自己出现在墙上
            self.assertIn("加入家庭", wall)
            browser.close()

    def test_a_drawing_lives_in_one_place_only(self):
        """同一批画不摆两处：画廊里有，「我的」里就不该再列一遍。

        以前「图鉴」收画完的、「我的」再按时间列一遍同样那些画，第二处永远是
        第一处的影子。现在画全在画廊（**没画完的也在**），「我的」只说用户自己。
        """
        if type(self) is not ZoomKeepsStrokesInCanvasSpace:
            self.skipTest("基类跑一次就够")
        anon = "anon-one-place"
        # 一张画完的 + 一张没画完的，都该挂在画廊里
        done = self._finish_one(anon)
        open_one = json.loads(urllib.request.urlopen(urllib.request.Request(
            self.base + "/api/sessions", method="POST",
            data=json.dumps({"quest_id": "imagine_animal",
                             "intent": {"emotion": "平静", "text": ""},
                             "participant": {"anon_id": anon}}).encode(),
            headers={"Content-Type": "application/json"})).read())["session_id"]

        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 820, "height": 1180})
            page.set_default_timeout(15000)
            page.add_init_script(f"""
              localStorage.setItem('artquest.tour/2', '1'); localStorage.setItem('artquest.acct_prompted', '1');
              localStorage.setItem('artquest.anon_id', {anon!r});
              sessionStorage.setItem('artquest.entered', '1');
            """)
            page.goto(self.base)
            page.wait_for_selector("#quest-grid > *")

            for _ in range(4):
                page.click(".tab[data-tab='dex']")
                try:
                    page.wait_for_selector("#view-dex:not(.hidden)", timeout=3000)
                    break
                except PWTimeout:
                    page.wait_for_timeout(300)
            page.wait_for_selector(f'.dex-open[data-sid="{done}"]')
            page.wait_for_selector(f'.dex-open[data-sid="{open_one}"]')      # 半张画也是画过的证据
            self.assertIn("还没画完", page.inner_text("#collection"))

            for _ in range(4):
                page.click(".tab[data-tab='me']")
                try:
                    page.wait_for_selector("#view-sessions:not(.hidden)", timeout=3000)
                    break
                except PWTimeout:
                    page.wait_for_timeout(300)
            page.wait_for_selector("#story .stile")
            me = page.inner_text("#view-sessions")
            self.assertNotIn("画过的画", me, "作品列表该整块搬去画廊了")
            self.assertEqual(page.locator("#view-sessions .dex-card").count(), 0)
            self.assertIn("画完的画", me)        # 小传说的是数字，不是一张张画
            browser.close()

    def test_the_researcher_code_is_not_a_thing_children_see(self):
        """心愿页上不该有「给自己起个代号」。

        代号是研究员分配的（`?pid=P007` 带进来），和后端名、本机代号、导出 JSON
        是同一类把手——这个项目定过它们不当界面给孩子看。孩子自己的身份是账号，
        起名在「我的」里；心愿这一屏（2026-09-26 简约风）只问心情和想画什么，
        连「起个名字」的提示都不摆——它只剩两个问题和一颗按钮。
        """
        if type(self) is not ZoomKeepsStrokesInCanvasSpace:
            self.skipTest("基类跑一次就够")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            try:
                page = browser.new_page(viewport={"width": 820, "height": 1180})
                page.set_default_timeout(15000)
                page.add_init_script("""
                  localStorage.setItem('artquest.tour/2', '1'); localStorage.setItem('artquest.acct_prompted', '1');
                  localStorage.setItem('artquest.anon_id', 'anon-no-code');
                  sessionStorage.setItem('artquest.entered', '1');
                """)
                page.goto(self.base)
                page.wait_for_selector("#quest-grid .quest-card")
                page.click("#quest-grid .quest-card")           # 选了就画：没有心愿屏
                page.wait_for_selector("#view-draw:not(.hidden)")

                self.assertTrue(page.is_hidden("#pidbox"), "代号框不该出现在孩子面前")
                # 画画屏右栏上除了任务本身什么说明都没有——多一句都算话多
                words = page.inner_text("#view-draw .brief")
                for banned in ("代号", "起个名字", "设备", "提示："):
                    self.assertNotIn(banned, words, f"画画屏上不该出现「{banned}」")

                # 研究员那条路还在：带 pid 进来，代号框出现并且已经填好
                page2 = browser.new_page(viewport={"width": 820, "height": 1180})
                page2.set_default_timeout(15000)
                page2.add_init_script("localStorage.setItem('artquest.tour/2', '1'); localStorage.setItem('artquest.acct_prompted', '1');"
                                      "sessionStorage.setItem('artquest.entered','1');")
                page2.goto(self.base + "/?study=1&pid=P07")
                page2.wait_for_selector("#quest-grid .quest-card")
                # 实验模式下 studybar 是异步补上去的，它一出现整张地图就往下挪一截；
                # 不等它落定就点，Playwright 会一直等一个「位置还在动」的元素
                page2.wait_for_selector("#studybar:not(.hidden)")
                page2.wait_for_timeout(600)
                # 实验模式下地图上摆的是 protocol 那条序列，任务一多，绝对定位的
                # 卡片会互相压住（点第一个会被一个 locked 的挡住）。这条测的是
                # 代号框露不露面，不是点击手感，所以直接让那张卡自己 click。
                page2.eval_on_selector("#quest-grid .quest-card:not(.locked)", "e => e.click()")
                page2.wait_for_selector("#view-draw:not(.hidden)")
                # 代号从 URL 进来就记住了，这次创作带着它
                self.assertEqual(page2.evaluate("localStorage.getItem('artquest.participant_id')"), "P07")
                self.assertIn("P07", page2.inner_text("#studybar"))
            finally:
                browser.close()

    def _finish_one(self, anon_id):
        """从服务端造一张画完的画——这条测的是界面怎么摆，不是画布。"""
        import base64
        import io

        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 240), "white")
        ImageDraw.Draw(img).ellipse((40, 40, 220, 200), fill=(120, 170, 230), outline="black", width=5)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

        def post(path, body):
            req = urllib.request.Request(self.base + path, method="POST",
                                         data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req).read())

        sid = post("/api/sessions", {"quest_id": "emotion_alone",
                                     "intent": {"emotion": "开心", "text": ""},
                                     "participant": {"anon_id": anon_id}})["session_id"]
        post(f"/api/sessions/{sid}/submit", {"image": url, "elapsed_ms": 60000, "phase": "before"})
        post(f"/api/sessions/{sid}/finalize", {"elapsed_ms": 62000})
        return sid

    def _start(self, page, intent, family=None):
        """Walk the real UI from the mission map into a running session.

        A first-time visitor gets the four-step guide over everything, so these
        tests arrive as a child who has already seen it — that is the state the
        gestures under test actually run in.
        """
        page.set_default_timeout(15000)
        page.add_init_script("localStorage.setItem('artquest.tour/2','1'); localStorage.setItem('artquest.acct_prompted','1')")
        page.goto(self.base)
        # 这个 app 开在彩点的世界上，地图在「进入世界」后面。
        #
        # 这里不能用 `is_visible`——它**问一次就走**：世界那一屏还在渲染、按钮
        # 还没画出来的那一瞬间问会得到 False，于是不点，然后一路等一张永远不会
        # 露面的关卡卡片（它在 DOM 里，但 #view-quest 已经被切成 hidden 了）。
        # 也不能等 `#view-quest:not(.hidden)`：初始 HTML 里 #view-quest 身上
        # 根本没有 hidden 类，那个选择器在 app 还没开始跑的时候就已经匹配上了。
        # 要等的是世界那一屏**真的出现**；`ui=quiet` 下它不出现，超时就是答案。
        try:
            page.wait_for_selector("#view-world:not(.hidden)", timeout=8000)
            page.click("#btn-enter-world")
        except PWTimeout:
            pass                      # quiet 模式直接落在地图上，没有这一步
        # `.quest-card` alone would resolve to the hidden card inside the draw
        # view before /api/quests lands, and a locator never re-queries
        page.wait_for_selector("#quest-grid .quest-card")
        if family:
            titles = page.eval_on_selector_all("#quest-grid .quest-card h3", "e=>e.map(x=>x.textContent)")
            page.eval_on_selector_all("#quest-grid .quest-card", f"(e)=>e[{titles.index(family)}].click()")
        else:
            page.click("#quest-grid .quest-card")
        page.wait_for_selector("#view-draw:not(.hidden)")      # 选了就画：没有心愿屏

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
            for _ in range(5):
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


    def test_a_colour_sucked_out_of_the_drawing_is_the_colour_that_was_painted(self):
        """吸管吸到的必须是画上真实的像素，而且那一下**不能顺手画出一笔**。

        取色器整个盖住画布，孩子想要「刚才那个红」只能凭记忆，所以给了吸管。
        它借的是落笔那条路（pointerdown 在画布上），最容易犯的错就是既吸了色
        又留下一个点。顺带盯住清空那个弹窗：点「继续画」画必须还在。
        """
        before = self._ids()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1180, "height": 820})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            self._start(page, "eyedropper")
            pick = lambda hx: (page.click("#btn-color"), page.wait_for_selector("#pop-color:not(.hidden)"),
                               page.eval_on_selector_all("#palette div", f"e => e.find(d => d.title === '{hx}').click()"))
            cur = lambda: page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--cur').trim()")

            pick("#e63946")                              # 红，粗一点，横穿画布中央画一笔
            page.eval_on_selector("#size", "e => { e.value = 80; e.dispatchEvent(new Event('input')); }")
            c = page.locator("#canvas").bounding_box()
            x, y = c["x"] + c["width"] / 2, c["y"] + c["height"] / 2
            page.mouse.move(x - 60, y); page.mouse.down(); page.mouse.move(x + 60, y, steps=6); page.mouse.up()
            pick("#222222")                              # 换回黑，吸管得把红找回来
            self.assertEqual(cur(), "#222222")

            page.click("#btn-color"); page.wait_for_selector("#pop-color:not(.hidden)")
            page.click("#btn-eyedrop")
            page.wait_for_selector("#eyedrop-tip:not(.hidden)")
            page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x + 10, y, steps=3)
            preview = page.evaluate("getComputedStyle(document.querySelector('#nib-dot')).backgroundColor")
            self.assertEqual(preview, "rgb(230, 57, 70)", "按住的时候泡泡里该是指尖下的颜色")
            page.mouse.up()
            self.assertEqual(cur(), "#e63946", "吸到的不是画上的红")
            self.assertTrue(page.evaluate("document.querySelector('#eyedrop-tip').classList.contains('hidden')"),
                            "松手之后吸管该自己收起来")
            self.assertTrue(page.eval_on_selector("#palette div[title='#e63946']", "e => e.classList.contains('active')"),
                            "吸到的是色板上有的颜色，色板上那格该亮")

            page.click("#btn-clear"); page.wait_for_selector("#clear-modal:not(.hidden)")
            page.click("#btn-clear-keep")
            still_red = page.evaluate(f"""() => {{
              const cv = document.querySelector('#canvas'), r = cv.getBoundingClientRect();
              const d = cv.getContext('2d').getImageData(Math.round(({x} - r.left) * cv.width / r.width),
                                                        Math.round(({y} - r.top) * cv.height / r.height), 1, 1).data;
              return [d[0], d[1], d[2]]; }}""")
            self.assertEqual(still_red, [230, 57, 70], "点了「继续画」，画却没了")

            page.wait_for_timeout(400)
            page.evaluate("ArtLog.flush()")
            page.wait_for_timeout(1200)
            page.click("#btn-submit")
            page.wait_for_timeout(4000)
            browser.close()

        self.assertEqual(errors, [], "JS errors on the page")
        sid = (self._ids() - before).pop()
        strokes = self._get(f"/api/sessions/{sid}/strokes")
        self.assertEqual(len(strokes), 1, f"吸管那一下不该留下笔画，现在有 {len(strokes)} 笔")
        self.assertEqual(strokes[0]["color"], "#e63946")
        from artquest.config import SESSIONS_DIR
        from artquest.storage import session_events
        events = session_events(SESSIONS_DIR / sid)
        sources = [(e.get("payload") or e.get("detail") or {}).get("source") for e in events if e.get("type") == "COLOR_CHANGE"]
        self.assertIn("eyedropper", sources, "从画里吸的颜色和从色板点的，日志里得分得开")

    def test_looking_at_the_reference_is_recorded_as_behaviour(self):
        """Look → draw → check → correct only exists if the reference records it."""
        errors, before = [], self._ids()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1500, "height": 1100})
            page.on("pageerror", lambda e: errors.append(str(e)))
            self._start(page, "reference", family="博物馆修复师")
            screen_of, drag, stroke_from = self._canvas_tools(page)

            # M1's reference is `mode: always`: the thumbnail sits in the column
            # from the start; the big view (where zoom/pan live) opens on tap
            page.wait_for_selector("#refpanel:not(.hidden)")
            page.click("#btn-ref-toggle")
            page.wait_for_selector("#ref-viewport", state="visible")
            page.wait_for_timeout(200)
            box = page.eval_on_selector("#ref-viewport",
                                        "e=>{const b=e.getBoundingClientRect();return [b.left,b.top,b.width,b.height]}")
            centre = (box[0] + box[2] / 2, box[1] + box[3] / 2)
            page.mouse.move(*centre)                           # attention: reference
            for _ in range(5):
                page.mouse.wheel(0, -120)                      # zoom into the reference
            page.wait_for_timeout(120)
            zoom = page.eval_on_selector("#ref-zoom", "e=>e.textContent")
            drag(centre, -40, -30)                             # pan it
            page.click("#btn-ref-close")                       # back to the canvas
            page.wait_for_timeout(200)
            stroke_from(300, 300, 80, 120)                     # attention: canvas
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
        self.assertFalse(shown["placeholder"], "参考图已经是真图了，事件里不该再标占位")
        # the switch back to the canvas is what makes look→draw→check countable
        self.assertLess(kinds.index("REFERENCE_FOCUS"), kinds.index("CANVAS_FOCUS"))


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class IPadGestures(ZoomKeepsStrokesInCanvasSpace):
    """One finger draws, two fingers navigate — and the log says which was which.

    On an iPad the child's second finger lands *after* the first has already
    touched the canvas, so a navigation gesture always starts with a stray mark.
    It is rolled back rather than kept, and rolled back visibly: `STROKE_CANCELLED`
    is in the timeline, so "this mark was not meant" stays readable instead of
    becoming a mystery dot or a missing stroke.
    """

    def test_two_fingers_navigate_without_moving_the_drawing(self):
        errors, before = [], self._ids()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1194, "height": 834},   # 11" iPad, landscape
                                    has_touch=True)
            page.on("pageerror", lambda e: errors.append(str(e)))
            self._start(page, "ipad gestures")
            cdp = page.context.new_cdp_session(page)

            def touch(kind, pts):
                cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [
                    {"x": x, "y": y, "id": i} for i, (x, y) in enumerate(pts)]})
                page.wait_for_timeout(28)

            def at(cx, cy):
                """Where canvas pixel (cx, cy) is on screen *right now* — the box has
                to be re-read, because zooming is what moves it."""
                return page.evaluate("""([cx, cy]) => {
                    const c = document.querySelector('#canvas'), r = c.getBoundingClientRect();
                    return [r.left + cx * r.width / c.width, r.top + cy * r.height / c.height];
                }""", [cx, cy])

            def finger_stroke(a, b, steps=6):
                pa, pb = at(*a), at(*b)
                touch("touchStart", [pa])
                for i in range(1, steps + 1):
                    touch("touchMove", [(pa[0] + (pb[0] - pa[0]) * i / steps,
                                         pa[1] + (pb[1] - pa[1]) * i / steps)])
                touch("touchEnd", [])

            finger_stroke((200, 200), (420, 330))          # 1. one finger draws

            c = at(500, 350)                                # 2. pinch to zoom in
            touch("touchStart", [(c[0] - 60, c[1]), (c[0] + 60, c[1])])
            for i in range(1, 9):
                k = 60 + i * 22
                touch("touchMove", [(c[0] - k, c[1]), (c[0] + k, c[1])])
            touch("touchEnd", [])
            page.wait_for_timeout(400)
            zoomed = page.eval_on_selector("#zoom-level", "e=>e.textContent")

            # 3. draw again, zoomed in — near the pinch focus, which is what is
            #    still on screen at ~4x
            finger_stroke((540, 380), (566, 398), steps=4)

            touch("touchStart", [(c[0] - 70, c[1]), (c[0] + 70, c[1])])   # 4. two-finger tap
            touch("touchEnd", [])
            page.wait_for_timeout(300)

            page.evaluate("ArtLog.flush()")
            page.wait_for_timeout(1500)
            browser.close()

        self.assertEqual(errors, [], "JS errors on the page")
        self.assertNotEqual(zoomed, "100%", "pinch did not zoom")

        sid = (self._ids() - before).pop()
        strokes = self._get(f"/api/sessions/{sid}/strokes")
        events = self._get(f"/api/sessions/{sid}")["events"]
        kinds = [e["type"] for e in events]

        # the two marks the child meant, and only those
        self.assertEqual(len(strokes), 2, strokes)
        self.assertEqual([s["pointer"] for s in strokes], ["touch", "touch"])
        # …landing in canvas pixels whatever the pinch did to the view
        for stroke, (want_x, want_y) in zip(strokes, [(200, 200), (540, 380)]):
            self.assertAlmostEqual(stroke["points"][0][0], want_x, delta=6, msg=stroke["stroke_id"])
            self.assertAlmostEqual(stroke["points"][0][1], want_y, delta=6, msg=stroke["stroke_id"])
        self.assertEqual(strokes[0]["zoom"], 1.0)
        self.assertGreater(strokes[1]["zoom"], 1.0)        # the second was drawn zoomed in

        # a finger is not a pen: pressure and tilt are absent, not invented
        for stroke in strokes:
            self.assertFalse(stroke["pressure_supported"])
            for pt in stroke["points"]:
                self.assertIsNone(pt[3], "pressure was fabricated")

        # every gesture's first finger left a mark that was rolled back, and said so
        self.assertEqual(kinds.count("STROKE_CANCELLED"), kinds.count("STROKE_START") - 2)
        self.assertGreaterEqual(kinds.count("STROKE_CANCELLED"), 1)
        # the gestures themselves are on the same timeline as wheel and buttons,
        # distinguishable only by source
        self.assertIn("pinch", [e["payload"].get("source") for e in events if e["type"] == "ZOOM"])
        self.assertIn("UNDO", kinds)                        # two-finger tap


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class OnAnApplePad(ZoomKeepsStrokesInCanvasSpace):
    """一块 pad 上的四件事：画布看得全、捏合不跳、装到主屏之后还打得开、
    孩子在画笔条上挑的颜色和浓淡服务端能原样重建出来。

    （四条合在一个类里，不是因为它们是一件事，而是因为每多一个继承基类的类，
    基类那一批就得整个重跑一遍。）

    **画布看得全**——孩子看得见的那个框，必须就是他画的那张画。

    样式表里写着 `canvas { max-height: 100% }`，但它**解析不出值**：
    .canvas-viewport 的高度是 flex 收缩出来的，specified height 还是 auto，
    百分比没有可依的高度，max-height 于是计算成 none——画布按宽度撑满、比框
    高出一截，被 overflow:hidden 切掉。iPad 横屏上下各切 22px（整幅画的 7.7%），
    1440x900 的桌面各切 16px。这不只是难看：构图是九维里的一维，而孩子从来
    没看全过他被评的那个框。所以上限由 app.js 的 fitCanvas() 按像素写进 style，
    这条测试盯着它别再退回去。
    """

    SIZES = [(1194, 834), (1180, 820), (1366, 1024), (820, 1180), (393, 852), (1440, 900)]

    def test_no_edge_of_the_canvas_is_cut_off(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            for w, h in self.SIZES:
                page = browser.new_page(viewport={"width": w, "height": h}, has_touch=True)
                self._start(page, f"fit {w}x{h}")
                page.wait_for_timeout(400)
                cut = page.evaluate("""() => {
                    const c = document.querySelector('#canvas'), v = document.querySelector('#viewport');
                    const a = c.getBoundingClientRect(), b = v.getBoundingClientRect();
                    return {top: b.top - a.top, bottom: a.bottom - b.bottom,
                            left: b.left - a.left, right: a.right - b.right,
                            w: a.width, h: a.height};
                }""")
                for side in ("top", "bottom", "left", "right"):
                    self.assertLess(cut[side], 2,
                                    f"{w}x{h}：画布{side}被切掉 {round(cut[side])}px（{cut['w']}x{cut['h']}）")
                # 切不掉了也不能缩成一张邮票：画布该占满能给它的那一边
                self.assertGreater(cut["w"] * cut["h"], 40000, f"{w}x{h}：画布只剩 {cut['w']}x{cut['h']}")
                page.close()
            browser.close()

    def test_a_pinch_keeps_the_point_under_the_fingers_still(self):
        """捏合的意思是「这儿放大」，不是「跳一下再放大」。

        手指给的是 clientX/clientY（整页的），view.tx/ty 量的是框内的位移，
        差着框的左上角。滚轮那条路一直减掉了 r.left/r.top，捏合那条路没减，
        所以在 iPad 上一捏，画面会整个甩掉一个顶栏的高度——大约 150px。
        只有触摸屏走这条路，鼠标测不出来。
        """
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1194, "height": 834}, has_touch=True)
            self._start(page, "pinch focus")
            cdp = page.context.new_cdp_session(page)

            def touch(kind, pts):
                cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [
                    {"x": x, "y": y, "id": i} for i, (x, y) in enumerate(pts)]})
                page.wait_for_timeout(28)

            def screen_of(cx, cy):
                return page.evaluate("""([cx, cy]) => {
                    const c = document.querySelector('#canvas'), r = c.getBoundingClientRect();
                    return [r.left + cx * r.width / c.width, r.top + cy * r.height / c.height];
                }""", [cx, cy])

            focus = (500, 350)
            fx, fy = screen_of(*focus)
            touch("touchStart", [(fx - 60, fy), (fx + 60, fy)])
            for i in range(1, 9):
                k = 60 + i * 22
                touch("touchMove", [(fx - k, fy), (fx + k, fy)])
            touch("touchEnd", [])
            page.wait_for_timeout(400)

            self.assertNotEqual(page.eval_on_selector("#zoom-level", "e=>e.textContent"), "100%")
            gx, gy = screen_of(*focus)
            browser.close()

        # 手指按住的那一点，放大之后还在手指底下
        self.assertAlmostEqual(gx, fx, delta=8, msg="捏合把画面横着甩开了")
        self.assertAlmostEqual(gy, fy, delta=8, msg="捏合把画面竖着甩开了")


    def _caches(self, page):
        return page.evaluate("""async () => {
            const names = await caches.keys(), out = [];
            for (const n of names) {
                const c = await caches.open(n);
                (await c.keys()).forEach(r => out.push(new URL(r.url).pathname));
            }
            return out;
        }""")

    def test_the_shell_is_kept_but_the_artwork_never_is(self):
        """装到主屏之后，它得像个 app：点开就在，wifi 抖一下不白屏。

        外壳（HTML/CSS/JS/字体/图标）存在设备上，**孩子的画一张都不存**。
        撤回是这个项目里唯一一处真删——要是 Service Worker 把作品留在了设备
        缓存里，撤回之后它还在，那条承诺就是假的。带身份的 API 同理：离线时该
        显示「连不上」，不该显示一份说不清是什么时候的旧数据。
        """
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            context = browser.new_context(viewport={"width": 820, "height": 1180}, has_touch=True)
            page = context.new_page()
            page.goto(self.base, wait_until="networkidle")
            page.wait_for_function("async () => { const r = await navigator.serviceWorker.getRegistration();"
                                   " return !!(r && r.active); }", timeout=15000)
            cached = self._caches(page)
            for must in ("/", "/static/app.js", "/static/style.css", "/static/log.js"):
                self.assertIn(must, cached, "外壳缺一块就打不开")

            # 走一遍真实流程，让画、日志、带身份的请求都跑过一次
            self._start(page, "pwa")
            page.wait_for_timeout(1200)
            leaked = [p for p in self._caches(page)
                      if p.startswith("/files/") or p.startswith("/api/sessions")
                      or p.startswith("/api/participants") or p == "/api/study"]
            self.assertEqual(leaked, [], f"这些不该留在设备缓存里：{leaked}")

            # 拔网线：外壳还打得开
            context.set_offline(True)
            offline = context.new_page()
            offline.goto(self.base, wait_until="domcontentloaded", timeout=15000)
            self.assertIn("彩绘冒险", offline.title())
            self.assertGreater(offline.eval_on_selector_all(".tab", "e => e.length"), 0,
                               "断网打开是一张白纸")
            browser.close()

    def test_the_colour_and_opacity_a_child_picked_survive_the_round_trip(self):
        """画笔条上挑的东西，必须一路走到服务端重建出来的那张图里。

        浓淡原来是工具写死的属性（`TOOLS[tool].alpha`），现在是孩子拉的滑杆。
        它敢放开，是因为 `reconstruct.py` 从来不查工具表——它按每一笔自己的
        `opacity` 合成，连同一笔自我重叠的 `1-(1-a)^k` 都算进去了。
        这条测试盯的就是那个「从来不查工具表」：浏览器画的和 PIL 重建的，
        在一个**非默认**的浓淡上也必须对得上，不然日志和作品就开始各说各话。
        """
        from artquest.reconstruct import check_final
        from artquest.config import SESSIONS_DIR

        before = self._ids()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1180, "height": 820}, has_touch=True)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            self._start(page, "brush round trip")

            # 取色器现在在常用色面板后面一层：点色块钮先浮出十二色，
            # 要精调才进取色器。两步都走一遍，顺带验证面板真的浮出来了。
            page.click("#btn-color")
            page.wait_for_selector("#pop-color:not(.hidden)")
            page.click("#btn-more-color")
            page.wait_for_selector("#color-modal:not(.hidden)")
            page.eval_on_selector("#pk-hue", "e => { e.value = 190; e.dispatchEvent(new Event('input')); }")
            box = page.locator("#pk-sv").bounding_box()
            page.mouse.click(box["x"] + box["width"] * 0.8, box["y"] + box["height"] * 0.25)
            picked = page.eval_on_selector("#pk-now-hex", "e => e.textContent").strip().lower()
            page.click("#pk-ok")

            # 一个**非默认**的浓淡：写死的工具值里没有 0.4，蒙不过去
            page.eval_on_selector("#opacity", "e => { e.value = 40; e.dispatchEvent(new Event('input')); }")
            page.eval_on_selector("#size", "e => { e.value = 55; e.dispatchEvent(new Event('input')); }")
            size_px = int(page.eval_on_selector("#size-val", "e => e.textContent"))

            c = page.locator("#canvas").bounding_box()
            for k in range(4):                      # 互相叠着画，逼出自我重叠那条路径
                x, y = c["x"] + c["width"] * (0.25 + k * 0.1), c["y"] + c["height"] * 0.3
                page.mouse.move(x, y)
                page.mouse.down()
                for i in range(1, 10):
                    page.mouse.move(x + i * 5, y + i * 16)
                page.mouse.up()
            page.wait_for_timeout(500)
            page.evaluate("ArtLog.flush()")
            page.wait_for_timeout(1200)
            page.click("#btn-submit")
            page.wait_for_timeout(4000)
            browser.close()

        self.assertEqual(errors, [], "JS errors on the page")
        sid = (self._ids() - before).pop()
        strokes = self._get(f"/api/sessions/{sid}/strokes")
        self.assertTrue(strokes, "没有笔画被记下来")
        for st in strokes:
            self.assertEqual(st["color"], picked, "取色器挑的颜色没进 stroke")
            self.assertAlmostEqual(st["opacity"], 0.4, places=2, msg="浓淡没进 stroke")
            self.assertEqual(st["size"], size_px, "粗细的非线性刻度和记下来的像素对不上")

        # 真正要紧的一条：服务端按这些数字重建，得和孩子看到的那张图一致
        report = check_final(SESSIONS_DIR / sid)
        self.assertIsNotNone(report["rel"], "没有 final.png 可比")
        self.assertLess(report["rel"], 0.30,
                        f"半透明的一笔重建不出来：rel={report['rel']}（阈值 0.30）")


if __name__ == "__main__":
    unittest.main()
