"""账号这条路，在真浏览器里从头走一遍。

Python 测试能证明归属规则是对的，证明不了「我的」那一屏上按钮点得着、
注册完名字真的出现在卡片上、换台设备（= 另一个 localStorage）登录之后
画过的画真的跟过来。这个项目里好几个 bug 只有真浏览器能发现，所以这条也真跑。

跳过条件同 `tests/test_browser`：没有 Playwright 或没有 Chrome 就跳过。
"""
import base64
import io
import json
import threading
import time
import unittest
import urllib.request

from .env import ADMIN, TMP as _TMP  # noqa: F401  (offline backends, throwaway data dir)
from .test_browser import _chrome_available, _free_port, sync_playwright  # noqa: E402


def _png_data_url():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (320, 240), "white")
    ImageDraw.Draw(img).ellipse((40, 40, 220, 200), fill=(120, 170, 230), outline="black", width=5)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@unittest.skipUnless(_chrome_available(), "playwright + chrome not available")
class AccountsInARealBrowser(unittest.TestCase):
    # 名字是全局唯一的，而同一次 `./test.sh` 里所有测试共用一个数据目录——
    # 写死的名字会和 tests/test_accounts.py 里注册过的撞上，然后这里收到 409。
    NAME = "满" + str(int(time.time()))[-6:]

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

    def _post(self, path, body):
        # 这里是**研究员**在服务端直接造数据（替某个账号记一幅画），所以带研究员令牌；
        # 界面里的孩子发同样的请求要拿自己账号的令牌
        req = urllib.request.Request(self.base + path, method="POST",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **ADMIN})
        return json.load(urllib.request.urlopen(req))

    def _finished_drawing(self, *, anon_id="", account_id=""):
        """一幅画完的画，直接从服务端造——这条测试要验的是界面，不是画布。"""
        r = self._post("/api/sessions", {
            "quest_id": "emotion_alone", "intent": {"emotion": "开心", "text": ""},
            "participant": {"anon_id": anon_id, "account_id": account_id}})
        sid = r["session_id"]
        self._post(f"/api/sessions/{sid}/submit",
                   {"image": _png_data_url(), "elapsed_ms": 1200, "phase": "before"})
        self._post(f"/api/sessions/{sid}/finalize", {"elapsed_ms": 1500})
        return sid

    def _open(self, browser, *, anon_id):
        """一台「设备」：自己的 localStorage，导览已经看过（这里不测导览）。"""
        ctx = browser.new_context(viewport={"width": 820, "height": 1180})
        ctx.add_init_script(f"""
          localStorage.setItem('artquest.tour/2', '1'); localStorage.setItem('artquest.acct_prompted', '1');
          localStorage.setItem('artquest.anon_id', {anon_id!r});
          sessionStorage.setItem('artquest.entered', '1');
        """)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        page.goto(self.base)
        page.wait_for_selector("#view-quest:not(.hidden)")
        return page

    def _tab(self, page, tab, view):
        # init() 结束时会自己 show 一次，所以在它跑完之前点 tab 会被拽回地图。
        # 「地图这一屏可见」不算信号——它在 HTML 里本来就是默认那一屏。
        # 等关卡真的渲染出来，再点；被拽回去就再点一次。
        # state="attached"：关卡渲染出来就算数。等「可见」的话，从别的 tab
        # 再调这个函数会永远超时——那时地图这一屏已经是 hidden 的了。
        page.wait_for_selector("#quest-grid > *", state="attached")
        for _ in range(4):
            page.click(f'.tab[data-tab="{tab}"]')
            try:
                page.wait_for_selector(f"#{view}:not(.hidden)", timeout=3000)
                return
            except Exception:
                page.wait_for_timeout(300)
        page.wait_for_selector(f"#{view}:not(.hidden)")

    def _me(self, page):
        self._tab(page, "me", "view-sessions")

    def _gallery(self, page):
        """画在画廊里，账号在「我的」里——这两屏从此是两件事。"""
        self._tab(page, "dex", "view-dex")

    def test_register_here_then_log_in_on_another_device(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            try:
                # -- 设备一：注册，然后画一张
                pad = self._open(browser, anon_id="anon-pad-ui")
                self._me(pad)
                self.assertTrue(pad.is_visible("#acct-out"), "没注册时该看见那段邀请")
                pad.click("#btn-acct-register")
                pad.fill("#acct-name-input", self.NAME)
                pad.fill("#acct-pin-input", "2468")
                pad.click("#btn-acct-go")
                pad.wait_for_selector("#acct-in:not(.hidden)")
                self.assertEqual(pad.inner_text("#acct-name"), self.NAME)
                self.assertTrue(pad.is_hidden("#acct-modal"))
                account_id = pad.evaluate("() => JSON.parse(localStorage.getItem('artquest.account')).account_id")

                sid = self._finished_drawing(anon_id="anon-pad-ui", account_id=account_id)
                pad.reload()
                self._gallery(pad)
                pad.wait_for_selector(f'.dex-open[data-sid="{sid}"]')

                # -- 设备二：另一个 localStorage，等于另一台设备
                phone = self._open(browser, anon_id="anon-phone-ui")
                self._gallery(phone)
                self.assertEqual(phone.locator(".dex-card").count(), 0, "新设备上不该先看见别人的画")
                self._me(phone)
                phone.click("#btn-acct-login")
                phone.fill("#acct-name-input", self.NAME)
                phone.fill("#acct-pin-input", "2468")
                phone.click("#btn-acct-go")
                phone.wait_for_selector("#acct-in:not(.hidden)")
                # 画跟着人过来了——这一条就是账号存在的全部理由
                self._gallery(phone)
                phone.wait_for_selector(f'.dex-open[data-sid="{sid}"]')
                self._me(phone)

                # 暗号错了要有一句看得懂的话，而且不掉线
                phone.once("dialog", lambda d: d.accept())      # 退出前的那句确认
                phone.click("#btn-acct-logout")
                phone.wait_for_selector("#view-welcome:not(.hidden)")   # 退出登录回最开始的门口
                phone.click("#btn-welcome-login")
                phone.fill("#acct-name-input", self.NAME)
                phone.fill("#acct-pin-input", "0000")
                phone.click("#btn-acct-go")
                phone.wait_for_selector("#acct-err:not(.hidden)")
                self.assertIn("不对", phone.inner_text("#acct-err"))
                self.assertTrue(phone.is_visible("#acct-modal"))
            finally:
                browser.close()

    def test_claiming_this_devices_older_drawings(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            try:
                anon = "anon-claim-ui"
                old = self._finished_drawing(anon_id=anon)      # 注册之前画的，没主人
                pad = self._open(browser, anon_id=anon)
                self._gallery(pad)
                pad.wait_for_selector(f'.dex-open[data-sid="{old}"]')   # 本机当然看得见
                self._me(pad)

                pad.click("#btn-acct-register")
                pad.fill("#acct-name-input", "领" + self.NAME)
                pad.fill("#acct-pin-input", "5656")
                pad.click("#btn-acct-go")
                pad.wait_for_selector("#acct-claim:not(.hidden)")
                self.assertIn("1 张", pad.inner_text("#acct-claim-text"))
                account_id = pad.evaluate("() => JSON.parse(localStorage.getItem('artquest.account')).account_id")

                # 认领之前：换台设备看不到它
                phone = self._open(browser, anon_id="anon-other-ui")
                phone.evaluate("""([t, a]) => {
                  localStorage.setItem('artquest.token', t);
                  localStorage.setItem('artquest.account', a);
                }""", [pad.evaluate("() => localStorage.getItem('artquest.token')"),
                       pad.evaluate("() => localStorage.getItem('artquest.account')")])
                phone.reload(); self._gallery(phone)
                self.assertEqual(phone.locator(f'.dex-open[data-sid="{old}"]').count(), 0)

                pad.click("#btn-acct-claim")
                pad.wait_for_selector("#acct-claim.hidden", state="attached")   # 收完就不再问

                phone.reload(); self._gallery(phone)
                phone.wait_for_selector(f'.dex-open[data-sid="{old}"]')
                self.assertTrue(account_id.startswith("acc-"))
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
