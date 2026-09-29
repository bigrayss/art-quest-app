"""账号：让一个孩子的画跟着**人**走，而不是跟着一台设备。

在这之前，身份只有一个 `anon_id`——浏览器 localStorage 里的一串随机字符。
它够用了很久，因为一台电脑就是一个孩子。但 app 一旦上了手机和 iPad，
「在 iPad 上画、在 iPhone 上看」是个**日常动作**，而 `anon_id` 让它根本不成立：
换台设备就是换个人，清一次缓存等于所有画消失。账号就是补这一件事，不是别的。

所以这里刻意**不做**的几样：没有邮箱、没有手机号、没有真名字段、没有密码强度要求、
没有头像上传。孩子注册时只给两样东西：一个自己起的名字，和四位数字暗号。
真实身份的隔离在另一套系统里（见 `docs/ETHICS.md`），账号不是身份，
它只是「这些画是同一个人画的」这句话的载体。

几条写进代码的规矩：

- **名字唯一但不可搜**：唯一是为了能登录，没有任何按名字列人的接口。
- **暗号只存 PBKDF2 摘要**，明文一秒都不留；连错 5 次冷却一分钟——
  四位数字一共一万种，没有这条就等于没有暗号。
- **注册/登录从不改写任何 session**。「把这台设备上以前画的收进我的」是
  一个**要孩子自己点**的动作，而且只认领**认领时刻之前**的作品
  （`devices[].until`）——共用一台 iPad 的教室里，下一个孩子退出登录后画的画
  不该悄悄落到上一个孩子名下。旧数据一个字节不动，这条和仓库里其他地方一致。
"""
import hashlib
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .logstore import read_json, write_json
from .storage import now_iso

PIN_LEN = 4
NAME_MAX = 12
_PBKDF2_ITER = 120_000
_MAX_TRIES = 5                 # 连错这么多次就冷却
_LOCK_SEC = 60
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
# account_id 会被直接拿来拼文件名，而它是从查询串里来的：只认自己发出去的那个形状
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AccountError(Exception):
    """带一个机器可读的 code 和一句给孩子看的话。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: Optional[datetime] = None) -> str:
    """和 session 的时间戳**同一种写法**（毫秒、UTC）。

    认领窗口是拿 `created_at <= until` 这样逐字符比出来的，两边精度不一样的话
    比较会在同一秒里翻车——秒级的 `+00:00` 排在毫秒级的 `.123+00:00` 前面。
    """
    return now_iso() if t is None else t.isoformat(timespec="milliseconds")


def name_key(name: str) -> str:
    """用来判重的形式：全角半角、大小写、中间的空格都不该算作两个名字。"""
    n = unicodedata.normalize("NFKC", name or "").strip().casefold()
    return re.sub(r"\s+", "", n)


def check_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name or "").strip()
    if _CTRL_RE.search(name):
        raise AccountError("bad_name", "名字里有打不出来的字符，换一个吧")
    if not name_key(name):
        raise AccountError("bad_name", "请输入名字")
    if len(name) > NAME_MAX:
        raise AccountError("bad_name", f"名字最多 {NAME_MAX} 个字")
    return name


def check_pin(pin: str) -> str:
    pin = (pin or "").strip()
    if not (len(pin) == PIN_LEN and pin.isdigit() and pin.isascii()):
        raise AccountError("bad_pin", f"密码是 {PIN_LEN} 位数字")
    return pin


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), _PBKDF2_ITER).hex()


def _token_key(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


class AccountStore:
    """`data/accounts/` 下的一堆小 JSON：一个账号一个文件，外加一张索引。

    索引把三种查法折成一个文件：名字（判重与登录）、设备（认领的历史）、
    令牌摘要（登录态）。它只存指针，账号本身的内容一律在账号文件里。
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or config.ACCOUNTS_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- 磁盘 --------------------------------------------------------------
    def _path(self, account_id: str) -> Path:
        return self.root / f"{account_id}.json"

    @property
    def _index_path(self) -> Path:
        return self.root / "index.json"

    def _index(self) -> Dict[str, Dict[str, str]]:
        idx = read_json(self._index_path) or {}
        for k in ("names", "devices", "tokens"):
            idx.setdefault(k, {})
        return idx

    def _write_index(self, idx: Dict[str, Any]) -> None:
        write_json(self._index_path, idx)

    def load(self, account_id: str) -> Optional[Dict[str, Any]]:
        if not account_id or not _ID_RE.match(account_id):
            return None
        return read_json(self._path(account_id))

    def _save(self, acc: Dict[str, Any]) -> Dict[str, Any]:
        write_json(self._path(acc["account_id"]), acc)
        return acc

    # -- 注册 / 登录 -------------------------------------------------------
    def register(self, name: str, pin: str, *, anon_id: str = "", buddy_name: str = "",
                 age: Optional[int] = None, role: str = "student") -> Dict[str, Any]:
        name = check_name(name)
        pin = check_pin(pin)
        idx = self._index()
        key = name_key(name)
        if key in idx["names"]:
            raise AccountError("name_taken", "这个名字已经有人用啦，换一个？")
        salt = secrets.token_hex(16)
        acc = {
            "account_id": "acc-" + secrets.token_hex(8),
            "name": name,
            "name_key": key,
            "created_at": _iso(),
            "last_seen_at": _iso(),
            # 暗号只以摘要的形式存在
            "pin": {"algo": "pbkdf2_sha256", "iter": _PBKDF2_ITER, "salt": salt, "hash": _hash_pin(pin, salt)},
            # 伙伴的名字跟着账号走，换台设备它还叫原来那个名字
            "buddy_name": (buddy_name or "").strip()[:16],
            # 年龄只用来推荐模式和做协变量；不填就是 None
            "age": int(age) if age is not None else None,
            # student | teacher。老师的令牌能进教师端（全部作品、打分）；学生的不能
            "role": "teacher" if role == "teacher" else "student",
            "devices": [],
            "failed": 0,
            "locked_until": None,
        }
        self._save(acc)
        idx["names"][key] = acc["account_id"]
        self._write_index(idx)
        token = self._issue_token(acc["account_id"])
        if anon_id:
            # 注册这一刻的设备先记下来，但**不认领**它上面的旧作品——
            # 认领要孩子自己点（见 claim_device）
            self._remember_device(acc["account_id"], anon_id, claim=False)
        return {"token": token, "account": self.public(self.load(acc["account_id"]))}

    def login(self, name: str, pin: str, *, anon_id: str = "") -> Dict[str, Any]:
        # 暗号的格式先验，**在查名字之前**：不然「格式不对」回 400、「名字不存在」回 401，
        # 光看状态码就能问出谁注册过。
        pin = check_pin(pin)
        key = name_key(name)
        account_id = self._index()["names"].get(key, "")
        acc = self.load(account_id) if account_id else None
        if not acc:
            # 名字不存在和暗号不对给同一句话：否则这个接口就成了「谁注册过」的查询器
            raise AccountError("bad_credentials", "名字或密码不对")
        locked = acc.get("locked_until")
        if locked and _iso() < locked:
            raise AccountError("locked", "试得太多啦，等一分钟再来")
        if not secrets.compare_digest(_hash_pin(pin, acc["pin"]["salt"]), acc["pin"]["hash"]):
            acc["failed"] = int(acc.get("failed") or 0) + 1
            if acc["failed"] >= _MAX_TRIES:
                acc["failed"] = 0
                acc["locked_until"] = _iso(_now() + timedelta(seconds=_LOCK_SEC))
            self._save(acc)
            raise AccountError("bad_credentials", "名字或密码不对")
        acc["failed"] = 0
        acc["locked_until"] = None
        acc["last_seen_at"] = _iso()
        self._save(acc)
        token = self._issue_token(acc["account_id"])
        if anon_id:
            self._remember_device(acc["account_id"], anon_id, claim=False)
        return {"token": token, "account": self.public(self.load(acc["account_id"]))}

    def reset_pin(self, name: str, new_pin: str, *, anon_id: str = "", by_admin: bool = False) -> Dict[str, Any]:
        """忘了暗号。没有邮箱、没有真名，能证明「这是我的账号」的只有两样：

        - **这台设备登录过这个账号**（`devices` 里有它的 anon_id）——孩子在自己画过画的 iPad 上
          可以直接改；别人在自己的设备上拿着一个名字改不了。
        - **研究员/老师**（管理员令牌）——课堂上孩子忘了就找老师，老师在教师端重设。

        旧令牌都留着：别的设备上仍然登录着，忘暗号不该把人从别处踢下线。改完在这台设备上直接登录。
        """
        new_pin = check_pin(new_pin)
        key = name_key(name)
        account_id = self._index()["names"].get(key, "")
        acc = self.load(account_id) if account_id else None
        if not acc:
            raise AccountError("bad_credentials", "没有这个名字")
        if not by_admin and not any(d.get("anon_id") == anon_id for d in acc.get("devices", []) if anon_id):
            raise AccountError("not_your_device", "只能在你登录过的设备上重设。换台设备，或者找老师帮你。")
        salt = secrets.token_hex(16)
        acc["pin"] = {"algo": "pbkdf2_sha256", "iter": _PBKDF2_ITER, "salt": salt, "hash": _hash_pin(new_pin, salt)}
        acc["failed"] = 0
        acc["locked_until"] = None
        acc["pin_reset_at"] = _iso()
        self._save(acc)
        token = self._issue_token(acc["account_id"])
        if anon_id:
            self._remember_device(acc["account_id"], anon_id, claim=False)
        return {"token": token, "account": self.public(self.load(acc["account_id"]))}

    # -- 登录态 ------------------------------------------------------------
    def _issue_token(self, account_id: str) -> str:
        token = secrets.token_hex(16)
        idx = self._index()
        idx["tokens"][_token_key(token)] = account_id
        self._write_index(idx)
        return token

    def by_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        return self.load(self._index()["tokens"].get(_token_key(token), ""))

    def require(self, token: str) -> Dict[str, Any]:
        acc = self.by_token(token)
        if not acc:
            raise AccountError("no_session", "登录已经过期，再登一次吧")
        return acc

    def logout(self, token: str) -> None:
        """只吊销这一台设备的令牌；别处仍然登录着。"""
        idx = self._index()
        if idx["tokens"].pop(_token_key(token), None) is not None:
            self._write_index(idx)

    def set_buddy_name(self, account_id: str, buddy_name: str) -> Dict[str, Any]:
        acc = self.load(account_id)
        if not acc:
            raise AccountError("no_session", "登录已经过期，再登一次吧")
        acc["buddy_name"] = (buddy_name or "").strip()[:16]
        return self.public(self._save(acc))

    # -- 设备 --------------------------------------------------------------
    def _remember_device(self, account_id: str, anon_id: str, *, claim: bool) -> Dict[str, Any]:
        acc = self.load(account_id)
        if not acc:
            raise AccountError("no_session", "登录已经过期，再登一次吧")
        row = next((d for d in acc["devices"] if d.get("anon_id") == anon_id), None)
        if row is None:
            row = {"anon_id": anon_id, "added_at": _iso(), "until": None}
            acc["devices"].append(row)
        if claim and not row.get("until"):
            # 认领的是**这一刻之前**这台设备上没有归属的画。写死时间点，
            # 是因为共用设备上「以后画的」不该跟着一起归过来。
            row["until"] = _iso()
            idx = self._index()
            idx["devices"].setdefault(anon_id, account_id)
            self._write_index(idx)
        self._save(acc)
        return acc

    def claim_device(self, account_id: str, anon_id: str) -> Dict[str, Any]:
        if not anon_id:
            raise AccountError("bad_device", "没认出这台设备")
        owner = self._index()["devices"].get(anon_id)
        if owner and owner != account_id:
            # 同一台设备上第二个孩子：他的旧画已经归了别人，不能再认领一次
            raise AccountError("device_taken", "这台设备上以前的画已经有主人啦")
        return self.public(self._remember_device(account_id, anon_id, claim=True))

    def device_windows(self, acc: Dict[str, Any]) -> Dict[str, str]:
        """{anon_id: 认领截止时刻}——只含真正认领过的设备，给 `SessionStore.list` 用。"""
        return {d["anon_id"]: d["until"] for d in (acc or {}).get("devices", [])
                if d.get("anon_id") and d.get("until")}

    # -- 撤回 --------------------------------------------------------------
    def delete(self, account_id: str) -> bool:
        """真删一个账号：账号文件 + 索引里所有指向它的名字、设备、令牌。

        撤回是这个项目里唯一一处"真删"（别处只标记）。孩子把同意收回去之后，
        作品要真的消失——一个还留着他起的名字的账号文件，等于那句承诺没兑现。
        作品本身由 `tools/withdraw.py` 删，这里只管账号。
        """
        acc = self.load(account_id)
        if not acc:
            return False
        idx = self._index()
        for bucket in ("names", "devices", "tokens"):
            idx[bucket] = {k: v for k, v in idx[bucket].items() if v != account_id}
        self._write_index(idx)
        self._path(account_id).unlink(missing_ok=True)
        return True

    # -- 对外形状 ----------------------------------------------------------
    def public(self, acc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """给前端的账号：暗号摘要、令牌、失败计数一律不出门。"""
        if not acc:
            return {}
        return {
            "account_id": acc["account_id"],
            "name": acc["name"],
            "created_at": acc.get("created_at", ""),
            "buddy_name": acc.get("buddy_name", ""),
            "age": acc.get("age"),
            "role": acc.get("role", "student"),
            # 只给数量：别的设备的代号，前端一个也用不上
            "devices": len(acc.get("devices", [])),
        }
