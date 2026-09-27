"""App 时代的接口契约：版本号、鉴权、跨源。

网页版一直靠「局域网 + SSH 隧道」这个信任假设兜着；iOS app 直接调公网上的 API，
每个请求都得自己证明身份，而且外壳跑在另一个源（artquest://app）上。这些测试守的是
那几条新规矩，以及「网页版一个字节没坏」——两个壳是同一份界面。
"""
import http.server
import json
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from .env import ADMIN, ADMIN_TOKEN, TMP as _TMP  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402

from artquest import config as cfg  # noqa: E402
from artquest.main import app  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

STATIC = Path(__file__).resolve().parent.parent / "static"


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


class TheApiHasAVersion(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def test_v1_and_the_bare_alias_are_the_same_api(self):
        """app 上架那天起孩子手机上的旧版本会一直调 /api/v1；`/api` 是当前版本的别名。"""
        a, b = self.c.get("/api/v1/config").json(), self.c.get("/api/config").json()
        self.assertEqual(a, b)
        r = self.c.post("/api/v1/sessions", json={"quest_id": "emotion_alone", "intent": {"emotion": "开心", "text": ""},
                                                  "participant": {"anon_id": "anon-v1"}})
        self.assertEqual(r.status_code, 201, r.text)
        sid = r.json()["session_id"]
        # 两个前缀看到的是同一份数据
        self.assertEqual(self.c.get(f"/api/sessions/{sid}").json()["session_id"], sid)
        self.assertEqual(self.c.get(f"/api/v1/sessions/{sid}").json()["session_id"], sid)

    def test_the_ios_shell_s_origin_passes_cors_preflight(self):
        """外壳从 artquest://app 发请求带着 Authorization，浏览器先问一句 OPTIONS。"""
        r = self.c.options("/api/v1/sessions", headers={
            "Origin": "artquest://app", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers.get("access-control-allow-origin"), "artquest://app")
        self.assertIn("authorization", r.headers.get("access-control-allow-headers", "").lower())
        # 别的源不行
        r = self.c.options("/api/v1/sessions", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        self.assertNotEqual(r.headers.get("access-control-allow-origin"), "https://evil.example")


class ResearcherEndpointsNeedTheToken(unittest.TestCase):
    """以前 `GET /api/sessions` 不带参数就把全服的 session id 一次发光，而 id 是 `/files/`
    和 `/api/sessions/{id}` 唯一的门。现在研究员那几条接口一律要 ARTQUEST_ADMIN_TOKEN。"""

    def setUp(self):
        self.c = TestClient(app)
        self.sid = self.c.post("/api/sessions", json={"quest_id": "emotion_alone",
                                                       "intent": {"emotion": "开心", "text": ""},
                                                       "participant": {"anon_id": "anon-admin-t"}}).json()["session_id"]

    def _locked(self, method, path, **kw):
        r = getattr(self.c, method)(path, **kw)
        self.assertEqual(r.status_code, 401, f"{method} {path} 没有令牌该是 401，得到 {r.status_code}")
        r = getattr(self.c, method)(path, headers=ADMIN, **kw)
        self.assertNotIn(r.status_code, (401, 403), f"{method} {path} 带研究员令牌不该被挡：{r.text}")

    def test_the_researcher_only_doors(self):
        self._locked("get", "/api/sessions")
        self._locked("post", "/api/gallery/curate", json={"k": 1})
        self._locked("post", f"/api/sessions/{self.sid}/rating", json={"source": "teacher", "rater_id": "T", "overall": 3})
        self._locked("post", f"/api/sessions/{self.sid}/annotation",
                     json={"rater_id": "E", "label": "planning", "t_start_ms": 0, "t_end_ms": 10})
        self._locked("get", f"/api/sessions/{self.sid}/annotation")
        self._locked("post", f"/api/sessions/{self.sid}/qc")
        self._locked("get", "/api/participants/P-X/protocol")

    def test_a_wrong_token_is_not_a_token(self):
        self.assertEqual(self.c.get("/api/sessions", headers=_bearer("nope")).status_code, 401)

    def test_no_token_configured_means_closed_not_open(self):
        """没设环境变量不是「都放行」，是「都关着」——公网上默认要安全。"""
        saved = cfg.ADMIN_TOKEN
        try:
            cfg.ADMIN_TOKEN = ""
            r = self.c.get("/api/sessions", headers=ADMIN)
            self.assertEqual(r.status_code, 401)
            self.assertIn("ARTQUEST_ADMIN_TOKEN", r.json()["detail"])
        finally:
            cfg.ADMIN_TOKEN = saved

    def test_the_child_s_own_doors_stay_open(self):
        """孩子那条路一步都不多：建作品、记笔画、交卷、看自己的，不需要任何令牌。"""
        self.assertEqual(self.c.get("/api/sessions", params={"anon_id": "anon-admin-t"}).status_code, 200)
        self.assertEqual(self.c.get(f"/api/sessions/{self.sid}").status_code, 200)
        self.assertEqual(self.c.post(f"/api/sessions/{self.sid}/log",
                                     json={"events": [], "strokes": [], "pending": 0}).status_code, 200)
        self.assertEqual(self.c.get("/api/participants/%20/growth", params={"anon_id": "anon-admin-t"}).status_code, 200)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _chrome_available():
    if sync_playwright is None:
        return False
    try:
        with sync_playwright() as pw:
            pw.chromium.launch(channel="chrome").close()
        return True
    except Exception:
        return False


class _ShellFiles(http.server.SimpleHTTPRequestHandler):
    """iOS 壳的替身：把 static/ 当网站端出去（`/` 是 index.html，`/static/x` 是文件），
    和 BundleSchemeHandler.swift 做的是同一件事，只是换成 http 好让 Chrome 打开。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def do_GET(self):
        # 真壳（artquest://）下 Service Worker 根本不注册；这里 http 会注册，
        # 所以不给 sw.js，免得测的是浏览器的 SW 而不是 app 的路径
        if self.path.split("?", 1)[0] == "/sw.js":
            self.send_error(404)
            return
        super().do_GET()

    def translate_path(self, path):
        path = path.split("?", 1)[0]
        if path in ("", "/"):
            path = "/index.html"
        if path.startswith("/static/"):
            path = path[len("/static"):]
        return super().translate_path(path)

    def log_message(self, *a):
        pass


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class TheShellRunsFromAnotherOrigin(unittest.TestCase):
    """app 里外壳和 API 不在同一个源上。这条在 Chrome 里把这件事真做一遍：
    外壳从第二个端口载入、注入 `window.ArtQuestNative`、API 走 `${server}/api/v1`
    并带 `Authorization`，令牌通过桥交给「钥匙串」。Swift 本身在这台机器上编不了，
    但 JS 这一半和服务器那一半——跨源、CORS、令牌流——全在这儿。"""

    @classmethod
    def setUpClass(cls):
        import uvicorn

        cls.api_port, cls.shell_port = _free_port(), _free_port()
        cls.api = f"http://127.0.0.1:{cls.api_port}"
        cls.shell = f"http://127.0.0.1:{cls.shell_port}"
        # 服务器要认这个源。正式配置里是 artquest://app；测试里的壳是 http 上的第二个端口。
        # CORSMiddleware 拿的是这同一个 list 对象，追加就生效。
        cfg.CORS_ORIGINS.append(cls.shell)
        cls.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cls.api_port, log_level="warning"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        cls.files = http.server.ThreadingHTTPServer(("127.0.0.1", cls.shell_port), _ShellFiles)
        cls.files_thread = threading.Thread(target=cls.files.serve_forever, daemon=True)
        cls.files_thread.start()
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.api + "/api/v1/config", timeout=1)
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.files.shutdown()
        cls.thread.join(timeout=5)
        try:
            cfg.CORS_ORIGINS.remove(cls.shell)
        except ValueError:
            pass

    def _get(self, path, token=""):
        req = urllib.request.Request(self.api + path, headers=_bearer(token) if token else ADMIN)
        return json.load(urllib.request.urlopen(req))

    def test_the_whole_login_and_drawing_path_crosses_origins(self):
        errors, native_msgs = [], []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            ctx = browser.new_context(viewport={"width": 1180, "height": 820}, has_touch=True)
            # 这就是 WebView.swift 里 bootScript() 注入的那一句，外加一个假的 webkit 桥把消息收起来
            ctx.add_init_script(f"""
              window.ArtQuestNative = {{ platform: "ios", server: {json.dumps(self.api)}, token: "", version: "test (0)" }};
              window.__native = [];
              window.webkit = {{ messageHandlers: {{ artquest: {{ postMessage: (m) => window.__native.push(m) }} }} }};
              localStorage.setItem('artquest.tour/2', '1');
              localStorage.setItem('artquest.anon_id', 'anon-shell');
              sessionStorage.setItem('artquest.entered', '1');
            """)
            page = ctx.new_page()
            page.set_default_timeout(20000)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(self.shell)
            # 地图渲染出来 = /api/v1/config、/quests、/families 三个跨源 GET 都成了
            page.wait_for_selector("#quest-grid .quest-card")
            self.assertEqual(page.evaluate("location.origin"), self.shell)

            # 「我的」→ 起个名字：POST 跨源，令牌回来后要交给钥匙串
            page.wait_for_selector("#quest-grid > *", state="attached")
            for _ in range(4):
                page.click('.tab[data-tab="me"]')
                try:
                    page.wait_for_selector("#view-sessions:not(.hidden)", timeout=3000)
                    break
                except Exception:
                    page.wait_for_timeout(300)
            page.click("#btn-acct-register")
            page.fill("#acct-name-input", "壳里人")
            page.fill("#acct-pin-input", "1357")
            page.click("#btn-acct-go")
            page.wait_for_selector("#acct-in:not(.hidden)")
            self.assertEqual(page.inner_text("#acct-name"), "壳里人")
            native_msgs = page.evaluate("window.__native")
            token = page.evaluate("window.ArtQuestNative.token")
            # 「这台设备 → 导出 JSON」指向服务器、只要本人的
            export = page.get_attribute("#export-link", "href")
            # 版本那一行说出 app 的版本
            shell_line = page.text_content("#shell-badge")   # 折在 <details> 里，inner_text 会是空的

            # 开一张画：POST /api/v1/sessions 跨源、带 Authorization（账号写在作品上）
            page.click('.tab[data-tab="map"]')
            page.wait_for_selector("#view-quest:not(.hidden)")
            page.click("#quest-grid .quest-card")
            page.wait_for_selector("#view-intent:not(.hidden)")
            page.click("#btn-start-draw")
            page.wait_for_selector("#view-draw:not(.hidden)")
            page.wait_for_function("() => document.querySelector('#recstat') && !document.querySelector('#recstat').classList.contains('hidden')")
            keep_awake = page.evaluate("window.__native.filter(m => m.type === 'keepAwake').map(m => m.on)")
            browser.close()

        # 假壳故意不给 sw.js（见 _ShellFiles），浏览器会为此记一条 404；真壳下 SW 根本不注册
        self.assertEqual([e for e in errors if "favicon" not in e and "fetching the script" not in e], [],
                         "页面里不该有 JS 报错")
        tokens = [m for m in native_msgs if m.get("type") == "token"]
        self.assertTrue(tokens and tokens[-1]["value"], "登录拿到的令牌要经桥交给钥匙串")
        self.assertEqual(tokens[-1]["value"], token)
        self.assertTrue(export.startswith(self.api + "/api/v1/sessions?"), export)
        self.assertIn("anon_id=anon-shell", export)
        self.assertIn("app test (0)", shell_line)
        self.assertIn(True, keep_awake, "进创作屏要告诉壳别锁屏")

        # 服务器那头：这个令牌能看到自己的画，画上写着账号 id，设备信息里记着是 app
        me = self._get("/api/v1/accounts/me", token=token)
        aid = me["account"]["account_id"]
        rows = self._get(f"/api/v1/sessions?account_id={aid}", token=token)
        self.assertEqual(len(rows), 1)
        meta = self._get(f"/api/v1/sessions/{rows[0]['session_id']}")
        self.assertEqual(meta["participant"]["account_id"], aid)
        self.assertEqual(meta["device"]["app"], {"platform": "ios", "version": "test (0)"})
        # 没有令牌，这个账号的画谁也列不出来
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(f"{self.api}/api/v1/sessions?account_id={aid}")
        self.assertEqual(cm.exception.code, 401)

    def _tab(self, page, name, view):
        page.wait_for_selector("#quest-grid > *", state="attached")
        for _ in range(4):
            page.click(f'.tab[data-tab="{name}"]')
            try:
                page.wait_for_selector(f"#{view}:not(.hidden)", timeout=3000)
                return
            except Exception:
                page.wait_for_timeout(300)

    def _boot(self, token, anon):
        """WebView.swift 里 bootScript() 注入的那一句 + 一个假的 webkit 桥把消息收起来。"""
        return f"""
          window.ArtQuestNative = {{ platform: "ios", server: {json.dumps(self.api)}, token: {json.dumps(token)}, version: "test (0)" }};
          window.__native = [];
          window.webkit = {{ messageHandlers: {{ artquest: {{ postMessage: (m) => window.__native.push(m) }} }} }};
          localStorage.setItem('artquest.tour/2', '1');
          localStorage.setItem('artquest.anon_id', {json.dumps(anon)});
          sessionStorage.setItem('artquest.entered', '1');
        """

    def test_a_whole_drawing_in_the_shell_and_what_the_bridge_hears(self):
        """从注册到结算页再到「删掉重装」，把壳里 JS 该对原生说的每一句都对一遍：
        令牌进钥匙串、进创作屏别锁屏、Pencil 双击切橡皮、徽章震一下、分享带着 PNG、
        重装后只靠钥匙串仍是登录态、退出时令牌清空。服务器那头核画归谁、笔画到齐、重放对得上。"""
        errors = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            ctx = browser.new_context(viewport={"width": 1180, "height": 820}, has_touch=True)
            ctx.add_init_script(self._boot("", "anon-shell-flow"))
            page = ctx.new_page()
            page.set_default_timeout(20000)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fetching the script" not in m.text else None)
            page.goto(self.shell)
            page.wait_for_selector("#quest-grid .quest-card")

            self._tab(page, "me", "view-sessions")
            page.click("#btn-acct-register")
            page.fill("#acct-name-input", "壳里画的")
            page.fill("#acct-pin-input", "2468")
            page.click("#btn-acct-go")
            page.wait_for_selector("#acct-in:not(.hidden)")
            token = page.evaluate("window.ArtQuestNative.token")
            self.assertTrue(token)
            aid = page.evaluate("JSON.parse(localStorage.getItem('artquest.account')).account_id")

            page.click('.tab[data-tab="map"]')
            page.wait_for_selector("#view-quest:not(.hidden)")
            page.click("#quest-grid .quest-card")
            page.wait_for_selector("#view-intent:not(.hidden)")
            page.click("#emotion-chips button")
            page.fill("#intent-text", "一座会走路的房子")
            page.click("#btn-start-draw")
            page.wait_for_selector("#view-draw:not(.hidden)")
            page.wait_for_function("() => !document.querySelector('#recstat').classList.contains('hidden')")
            self.assertIn(True, page.evaluate("window.__native.filter(m=>m.type==='keepAwake').map(m=>m.on)"),
                          "进创作屏要告诉壳别锁屏")

            def stroke(cx, cy, dx, dy):
                a = page.evaluate("([cx,cy]) => { const c=document.querySelector('#canvas'), r=c.getBoundingClientRect();"
                                  " return [r.left+cx*r.width/c.width, r.top+cy*r.height/c.height]; }", [cx, cy])
                page.mouse.move(*a)
                page.mouse.down()
                page.mouse.move(a[0] + dx, a[1] + dy, steps=10)
                page.mouse.up()
            for i in range(6):
                stroke(150 + i * 90, 200 + (i % 2) * 120, 120, 70)
            # Pencil 双击（壳转发成 artquest:pencilTap）：橡皮 ↔ 刚才那支
            tool = lambda: page.evaluate("document.querySelector('#tools button.active').dataset.tool")
            before = tool()
            page.evaluate("window.dispatchEvent(new Event('artquest:pencilTap'))")
            self.assertEqual(tool(), "eraser")
            page.evaluate("window.dispatchEvent(new Event('artquest:pencilTap'))")
            self.assertEqual(tool(), before)
            stroke(300, 500, 200, -40)
            page.evaluate("ArtLog.flush()")
            page.wait_for_timeout(1500)

            page.click("#btn-submit")
            page.wait_for_selector("#btn-skip-revise:visible", timeout=30000)
            page.click("#btn-skip-revise")
            try:
                page.wait_for_selector("#btn-survey-skip:visible", timeout=5000)
                page.click("#btn-survey-skip")
            except Exception:
                pass
            page.wait_for_selector("#view-final:not(.hidden)", timeout=30000)
            page.wait_for_timeout(1500)
            self.assertFalse(page.evaluate("window.__native.filter(m=>m.type==='keepAwake').slice(-1)[0].on"),
                             "离开创作屏要把锁屏还回去")
            self.assertGreater(page.evaluate("document.querySelectorAll('#badges .badge').length"), 0)
            self.assertGreaterEqual(page.evaluate("window.__native.filter(m=>m.type==='haptic').length"), 1,
                                    "点亮徽章要震一下")
            self.assertTrue(page.is_visible("#btn-share"), "分享只在 app 里有，这儿是 app")
            page.click("#btn-share")
            share = [m for m in page.evaluate("window.__native") if m.get("type") == "share"]
            self.assertTrue(share and share[-1]["image"].startswith("data:image/png;base64,") and share[-1]["title"])
            page.click("#btn-again")
            page.wait_for_selector("#view-quest:not(.hidden)")
            self._tab(page, "dex", "view-dex")
            page.wait_for_selector(".dex-card img", timeout=10000)
            self.assertTrue(page.evaluate("document.querySelector('.dex-card img').src").startswith(self.api + "/files/"),
                            "画廊缩略图要指向服务器")
            ctx.close()

            # 「删掉重装」：新 context，localStorage 全空，只有钥匙串里那个令牌
            ctx2 = browser.new_context(viewport={"width": 1180, "height": 820})
            ctx2.add_init_script(self._boot(token, "anon-shell-reinstall"))
            p2 = ctx2.new_page()
            p2.set_default_timeout(20000)
            p2.on("pageerror", lambda e: errors.append(str(e)))
            p2.on("dialog", lambda d: d.accept())
            p2.goto(self.shell)
            self._tab(p2, "me", "view-sessions")
            p2.wait_for_selector("#acct-in:not(.hidden)", timeout=10000)
            self.assertEqual(p2.inner_text("#acct-name"), "壳里画的", "重装后只靠钥匙串仍该是登录态")
            self._tab(p2, "dex", "view-dex")
            p2.wait_for_selector(".dex-card", timeout=10000)
            self._tab(p2, "me", "view-sessions")
            p2.click("#btn-acct-logout")
            p2.wait_for_selector("#acct-out:not(.hidden)")
            last = [m for m in p2.evaluate("window.__native") if m.get("type") == "token"][-1]
            self.assertEqual(last["value"], "", "退出要让壳把钥匙串里的令牌清掉")
            browser.close()

        self.assertEqual(errors, [], "页面里不该有 JS 报错")
        # 令牌刚在上面「退出」时吊销了，下面用研究员令牌替这个账号问
        rows = self._get(f"/api/v1/sessions?account_id={aid}")
        self.assertEqual([r["status"] for r in rows], ["done"])
        sid = rows[0]["session_id"]
        meta = self._get(f"/api/v1/sessions/{sid}")
        self.assertEqual(meta["participant"]["account_id"], aid, "画上要写着账号")
        self.assertEqual(meta["device"]["app"], {"platform": "ios", "version": "test (0)"})
        strokes = self._get(f"/api/v1/sessions/{sid}/strokes")
        self.assertGreaterEqual(len(strokes), 7)
        self.assertTrue(all(s["points"][0][3] is None for s in strokes), "鼠标的压感是 null，不是 0.5")
        self.assertNotIn("replay_matches_final", (meta.get("quality") or {}).get("failed", []))
        self.assertTrue(any(e.get("type") == "BRUSH_CHANGE" and (e.get("payload") or {}).get("source") == "pencil_tap"
                            for e in meta.get("events", [])), "笔杆上切的工具要记成 pencil_tap")


if __name__ == "__main__":
    unittest.main()
