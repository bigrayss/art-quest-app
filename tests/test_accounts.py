"""账号：让画跟着人走，而不是跟着一台设备。

这些测试盯着的不是「注册能不能成功」，而是账号引进来的那几个新的出错方式：
共用一台 iPad 的两个孩子会不会看见对方的画、认领会不会把别人的画顺走、
换台设备登录之后伙伴还认不认得你。
"""
import base64
import io
import unittest

from .env import TMP as _TMP, ADMIN  # noqa: F401  sets the offline backends and the test data dir

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from artquest.accounts import AccountError, AccountStore, name_key  # noqa: E402
from artquest.main import app, store  # noqa: E402


def _png():
    img = Image.new("RGB", (300, 220), "white")
    ImageDraw.Draw(img).ellipse((40, 40, 200, 180), fill=(220, 120, 60), outline="black", width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _draw(c, *, anon_id="", account_id="", token="", quest_id="emotion_alone"):
    """画完一整幅——这些用例只关心它归谁，不关心画了什么。
    说这幅画是某个账号的，就得带那个账号的令牌（`token`）。"""
    r = c.post("/api/sessions", json={
        "quest_id": quest_id, "intent": {"emotion": "开心", "text": ""},
        "participant": {"anon_id": anon_id, "account_id": account_id},
    }, headers=_bearer(token) if token else {})
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    c.post(f"/api/sessions/{sid}/submit", json={"image": _png(), "elapsed_ms": 1000, "phase": "before"})
    c.post(f"/api/sessions/{sid}/finalize", json={"elapsed_ms": 1200})
    return sid


class Registration(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)

    def test_register_then_login_from_another_device(self):
        r = self.c.post("/api/accounts/register",
                        json={"name": "小满", "pin": "2468", "anon_id": "anon-ipad", "buddy_name": "阿布"})
        self.assertEqual(r.status_code, 201)
        acc = r.json()["account"]
        self.assertEqual(acc["name"], "小满")
        self.assertNotIn("pin", acc)                      # 暗号摘要不出门
        r2 = self.c.post("/api/accounts/login", json={"name": "小满", "pin": "2468", "anon_id": "anon-phone"})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["account"]["account_id"], acc["account_id"])
        # 伙伴的名字跟着账号走，新设备上不用重起一次
        self.assertEqual(r2.json()["account"]["buddy_name"], "阿布")
        self.assertNotEqual(r2.json()["token"], r.json()["token"])   # 一台设备一个令牌

    def test_name_is_taken_only_once(self):
        self.c.post("/api/accounts/register", json={"name": "重名", "pin": "1111"})
        again = self.c.post("/api/accounts/register", json={"name": " 重名 ", "pin": "2222"})
        self.assertEqual(again.status_code, 409)
        self.assertIn("换一个", again.json()["detail"])

    def test_bad_pin_says_nothing_about_the_name(self):
        self.c.post("/api/accounts/register", json={"name": "猜猜看", "pin": "1357"})
        wrong = self.c.post("/api/accounts/login", json={"name": "猜猜看", "pin": "0000"})
        missing = self.c.post("/api/accounts/login", json={"name": "根本没这个人", "pin": "0000"})
        self.assertEqual(wrong.status_code, 401)
        # 两句话必须一模一样，否则这个接口就成了「谁注册过」的查询器
        self.assertEqual(wrong.json()["detail"], missing.json()["detail"])
        # 连格式不对的暗号也要一视同仁：光看状态码也不该问出谁注册过
        here = self.c.post("/api/accounts/login", json={"name": "猜猜看", "pin": "12"})
        nowhere = self.c.post("/api/accounts/login", json={"name": "根本没这个人", "pin": "12"})
        self.assertEqual(here.status_code, nowhere.status_code)

    def test_pin_must_be_four_digits(self):
        r = self.c.post("/api/accounts/register", json={"name": "短暗号", "pin": "12"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("位数字", r.json()["detail"])

    def test_too_many_wrong_pins_cools_down(self):
        self.c.post("/api/accounts/register", json={"name": "试很多次", "pin": "9090"})
        codes = [self.c.post("/api/accounts/login", json={"name": "试很多次", "pin": "0001"}).status_code
                 for _ in range(6)]
        self.assertEqual(codes[-1], 429)          # 四位数字一共一万种，没有冷却等于没有暗号
        # 冷却期间连正确的暗号也先挡住
        self.assertEqual(self.c.post("/api/accounts/login",
                                     json={"name": "试很多次", "pin": "9090"}).status_code, 429)

    def test_logout_only_drops_this_device(self):
        reg = self.c.post("/api/accounts/register", json={"name": "两台", "pin": "1212"}).json()
        other = self.c.post("/api/accounts/login", json={"name": "两台", "pin": "1212"}).json()
        self.c.post("/api/accounts/logout", json={"token": reg["token"]})
        self.assertEqual(self.c.get("/api/accounts/me", params={"token": reg["token"]}).status_code, 401)
        self.assertEqual(self.c.get("/api/accounts/me", params={"token": other["token"]}).status_code, 200)


class WhoseDrawingIsIt(unittest.TestCase):
    """账号引进来的真正风险：一台设备上不止一个孩子。"""

    def setUp(self):
        self.c = TestClient(app)

    def test_work_follows_the_child_to_another_device(self):
        reg = self.c.post("/api/accounts/register", json={"name": "跨设备", "pin": "3434"}).json()
        acc = reg["account"]
        sid = _draw(self.c, anon_id="anon-ipad-1", account_id=acc["account_id"], token=reg["token"])
        # 手机上：设备代号是另一个，令牌也是另一台设备登录拿到的，但账号是同一个
        phone = self.c.post("/api/accounts/login", json={"name": "跨设备", "pin": "3434"}).json()["token"]
        rows = self.c.get("/api/sessions", params={"anon_id": "anon-phone-1",
                                                   "account_id": acc["account_id"]}, headers=_bearer(phone)).json()
        self.assertIn(sid, [r["session_id"] for r in rows])

    def test_saying_you_are_someone_takes_their_token(self):
        """`account_id` 以前是谁传谁生效。现在说自己是谁，就得拿那个账号的令牌。"""
        a = self.c.post("/api/accounts/register", json={"name": "真身", "pin": "1122"}).json()
        b = self.c.post("/api/accounts/register", json={"name": "冒名", "pin": "3344"}).json()
        sid = _draw(self.c, anon_id="anon-a", account_id=a["account"]["account_id"], token=a["token"])
        aid = a["account"]["account_id"]
        # 不带令牌：401；带别人的令牌：403；两种都一张画也拿不到
        self.assertEqual(self.c.get("/api/sessions", params={"account_id": aid}).status_code, 401)
        self.assertEqual(self.c.get("/api/sessions", params={"account_id": aid},
                                    headers=_bearer(b["token"])).status_code, 403)
        # 把画记到别人名下也一样
        r = self.c.post("/api/sessions", json={"quest_id": "emotion_alone", "intent": {"emotion": "开心", "text": ""},
                                               "participant": {"anon_id": "anon-b", "account_id": aid}},
                        headers=_bearer(b["token"]))
        self.assertEqual(r.status_code, 403)
        # 研究员可以替任何人问
        self.assertIn(sid, [x["session_id"] for x in
                            self.c.get("/api/sessions", params={"account_id": aid}, headers=ADMIN).json()])
        # 令牌放在 `Authorization` 里，`/me` 不再需要 `?token=`
        me = self.c.get("/api/accounts/me", headers=_bearer(a["token"])).json()
        self.assertEqual(me["account"]["account_id"], aid)

    def test_a_ticket_spent_offline_needs_no_token_at_replay(self):
        """票是联网时拿着令牌领的，账号那会儿就核过了。离线画完重放的时候
        孩子可能已经退出登录——那幅画不能因此丢在半路。"""
        reg = self.c.post("/api/accounts/register", json={"name": "离线票", "pin": "5566"}).json()
        aid = reg["account"]["account_id"]
        # 没令牌领不到写着账号的票
        self.assertEqual(self.c.post("/api/tickets", json={"n": 1, "participant": {"account_id": aid}}).status_code, 401)
        t = self.c.post("/api/tickets", json={"n": 1, "participant": {"anon_id": "anon-t", "account_id": aid}},
                        headers=_bearer(reg["token"])).json()["tickets"][0]
        self.c.post("/api/accounts/logout", json={"token": reg["token"]})
        r = self.c.post("/api/sessions", json={"quest_id": "emotion_alone", "session_id": t["session_id"],
                                               "intent": {"emotion": "开心", "text": ""},
                                               "participant": {"anon_id": "anon-t", "account_id": aid}})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(store.load(t["session_id"])["participant"]["account_id"], aid)
        # 但拿一张别人的票号也换不来别人的身份
        other = self.c.post("/api/accounts/register", json={"name": "别人", "pin": "7788"}).json()
        r = self.c.post("/api/sessions", json={"quest_id": "emotion_alone", "session_id": t["session_id"],
                                               "intent": {"emotion": "开心", "text": ""},
                                               "participant": {"anon_id": "anon-t", "account_id": other["account"]["account_id"]}})
        self.assertEqual(r.status_code, 401)

    def test_an_accounts_work_never_leaks_to_the_next_child(self):
        a = self.c.post("/api/accounts/register", json={"name": "甲", "pin": "1010"}).json()
        b = self.c.post("/api/accounts/register", json={"name": "乙", "pin": "2020"}).json()
        shared = "anon-shared-ipad"
        mine = _draw(self.c, anon_id=shared, account_id=a["account"]["account_id"], token=a["token"])
        # 同一台 iPad，换个孩子登录
        rows = self.c.get("/api/sessions", params={"anon_id": shared, "account_id": b["account"]["account_id"]},
                          headers=_bearer(b["token"])).json()
        self.assertNotIn(mine, [r["session_id"] for r in rows])
        # 退出登录之后，设备代号也带不走它
        rows = self.c.get("/api/sessions", params={"anon_id": shared}).json()
        self.assertNotIn(mine, [r["session_id"] for r in rows])

    def test_claiming_takes_only_what_was_here_before(self):
        anon = "anon-claim"
        old = _draw(self.c, anon_id=anon)                       # 注册之前画的，没有主人
        reg = self.c.post("/api/accounts/register",
                          json={"name": "认领", "pin": "5656", "anon_id": anon}).json()
        me = self.c.get("/api/accounts/me", params={"token": reg["token"], "anon_id": anon}).json()
        self.assertEqual(me["unclaimed_here"], 1)
        self.assertFalse(me["claimed_here"])
        # 认领之前，别的设备上看不到它
        acc_id, hdr = reg["account"]["account_id"], _bearer(reg["token"])
        far = self.c.get("/api/sessions", params={"anon_id": "anon-elsewhere", "account_id": acc_id}, headers=hdr).json()
        self.assertNotIn(old, [r["session_id"] for r in far])

        self.c.post("/api/accounts/claim", json={"token": reg["token"], "anon_id": anon})
        far = self.c.get("/api/sessions", params={"anon_id": "anon-elsewhere", "account_id": acc_id}, headers=hdr).json()
        self.assertIn(old, [r["session_id"] for r in far])

        # 认领之后，同一台设备上无账号画的画不再跟着走——那可能是下一个孩子
        later = _draw(self.c, anon_id=anon)
        far = self.c.get("/api/sessions", params={"anon_id": "anon-elsewhere", "account_id": acc_id}, headers=hdr).json()
        self.assertNotIn(later, [r["session_id"] for r in far])

    def test_a_device_can_only_be_claimed_once(self):
        anon = "anon-contested"
        _draw(self.c, anon_id=anon)
        first = self.c.post("/api/accounts/register",
                            json={"name": "先来", "pin": "7070", "anon_id": anon}).json()
        second = self.c.post("/api/accounts/register",
                             json={"name": "后到", "pin": "8080", "anon_id": anon}).json()
        self.c.post("/api/accounts/claim", json={"token": first["token"], "anon_id": anon})
        r = self.c.post("/api/accounts/claim", json={"token": second["token"], "anon_id": anon})
        self.assertEqual(r.status_code, 409)

    def test_growth_follows_the_account(self):
        reg = self.c.post("/api/accounts/register", json={"name": "成长", "pin": "4321"}).json()
        acc = reg["account"]
        _draw(self.c, anon_id="anon-g1", account_id=acc["account_id"], token=reg["token"])
        g = self.c.get("/api/participants/%20/growth",
                       params={"anon_id": "anon-g2", "account_id": acc["account_id"]}, headers=_bearer(reg["token"])).json()
        self.assertEqual(g["n_tasks"], 1)       # 换台设备，伙伴不用从头长起

    def test_an_unknown_account_id_matches_nothing(self):
        """认不出来的账号 id 不能退回全量视图——那是「我的」接口最容易出的漏。"""
        sid = _draw(self.c, anon_id="anon-unknown-test")
        # 没有令牌，一个认不出来的账号 id 连门都进不去
        self.assertEqual(self.c.get("/api/sessions", params={"account_id": "acc-nonexistent"}).status_code, 401)
        # 研究员替它问，也只该得到空的——不能退回全量
        rows = self.c.get("/api/sessions", params={"account_id": "acc-nonexistent"}, headers=ADMIN).json()
        self.assertNotIn(sid, [r["session_id"] for r in rows])
        self.assertEqual(rows, [])
        # 路径穿越也只是一个认不出来的 id，不会落到文件系统上
        self.assertEqual(self.c.get("/api/sessions", params={"account_id": "../../etc"}, headers=ADMIN).json(), [])

    def test_researcher_view_still_sees_everything(self):
        reg = self.c.post("/api/accounts/register", json={"name": "全量", "pin": "6543"}).json()
        acc = reg["account"]
        sid = _draw(self.c, anon_id="anon-r", account_id=acc["account_id"], token=reg["token"])
        self.assertIn(sid, [r["session_id"] for r in self.c.get("/api/sessions", headers=ADMIN).json()])
        # 作品里存的是账号 id，不是孩子起的名字——名字只住在账号文件里
        meta = store.load(sid)
        self.assertEqual(meta["participant"]["account_id"], acc["account_id"])
        self.assertNotIn("全量", str(meta))


class Withdrawal(unittest.TestCase):
    """撤回是这个项目唯一一处真删——账号里有孩子起的名字，它也得走。"""

    def test_withdraw_can_take_the_account_with_it(self):
        from artquest.accounts import AccountStore
        from tools import withdraw as withdraw_tool

        c = TestClient(app)
        reg = c.post("/api/accounts/register",
                     json={"name": "要撤回的", "pin": "1919", "anon_id": "anon-wd"}).json()
        acc_id = reg["account"]["account_id"]
        sid = _draw(c, anon_id="anon-wd", account_id=acc_id, token=reg["token"])

        dry = withdraw_tool.withdraw("P-wd", account_id=acc_id)
        self.assertTrue(dry["dry_run"])
        self.assertIn(sid, dry["session_ids"])
        self.assertEqual(dry["accounts_seen"], [acc_id])      # 回执点出还有个账号要处理
        self.assertTrue(AccountStore().load(acc_id))          # dry run 什么都不动

        done = withdraw_tool.withdraw("P-wd", account_id=acc_id, confirm=True)
        self.assertTrue(done["account_removed"])
        self.assertIsNone(AccountStore().load(acc_id))
        # 名字也跟着释放：撤回之后别人能再用这个名字注册
        self.assertEqual(c.post("/api/accounts/register",
                                json={"name": "要撤回的", "pin": "2929"}).status_code, 201)
        self.assertEqual(c.post("/api/accounts/login",
                                json={"name": "要撤回的", "pin": "1919"}).status_code, 401)


class StoreRules(unittest.TestCase):
    def test_name_key_folds_case_width_and_spaces(self):
        self.assertEqual(name_key(" Ｍiao 猫 "), name_key("miao猫"))

    def test_control_characters_are_not_a_name(self):
        with self.assertRaises(AccountError):
            AccountStore().register("坏\x00名字", "1234")


if __name__ == "__main__":
    unittest.main()
