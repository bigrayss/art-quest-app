"""FastAPI application: serves the drawing UI and the session / research API."""
import hashlib
import json
import logging
import re
import secrets
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import config as cfg   # 不叫 config：下面 /api/config 那个端点函数就叫这个名字
from . import events as ev
from . import gallery as gallery_mod
from . import history as history_mod
from . import study as study_mod
from .accounts import AccountError, AccountStore
from . import i18n
from . import teacher_pool
from .config import (CLAUDE_MODEL, SESSIONS_DIR, SNAPSHOT_INTERVAL_SEC, STATIC_DIR,
                     claude_available)
from .assist import get_assist_engine
from .feedback import get_feedback_engine
from .personalize import MODES as HISTORY_MODES, get_personalizer
from .qc import check as qc_check
from .quests import (EMOTIONS, QUESTS, QUESTS_BY_ID, condition_snapshot,
                     families as task_families)
from .reconstruct import check_final
from .rubric import apply_contract, check_rating
from .revision import attribute as attribute_revision
from .schemas import (
    Opinion,
    TeacherPoolUpdate,
    AssistIn,Abandon, Annotation, ClaimDevice, CreateSession, Curate, DrawEvent, EarnedBadges,
                      FeaturedAnswer, FeedbackIn, Finalize, HARDEST_PARTS_SHOWN, IssueTickets, Login, LogBatch,
                      PROCESS_LABELS, ProfileUpdate, Questionnaire, Rating, Register, ResetPin, Snapshot, TeacherGrade, StudyAssign,
                      Stroke, Submit, TokenOnly)
from .scoring import DIMENSIONS, SCALE_MAX, get_scorer
from .scoring.levels import rubric_payload
from .storage import (SCHEMA_VERSION, SessionStore, belongs_to as storage_belongs_to,
                      decode_data_url, now_iso, sid_of)

log = logging.getLogger("artquest")

# Bumped whenever the feedback prompts change, so text generated under different
# instructions is never pooled in analysis.
PROMPT_VERSION = "feedback/1"

# 外壳（HTML/CSS/JS）的版本号 = 这几个文件内容的哈希。
# 谁也不用记得去改它：改了任何一个文件，版本就变了。
# 两个地方用它——Service Worker 的缓存名，和「我的 → 这台设备」里显示的那一行。
# 以前 sw.js 里写死一个 `v3`，改完前端忘了跟着 bump，装在 iPad 主屏上的那份
# 就一直拿旧外壳；而且当时**没有任何地方看得出设备上跑的是哪一版**，
# 于是「到底更新了没有」只能靠猜。
_SHELL_FILES = ("index.html", "app.js", "log.js", "style.css", "sw.js", "i18n.js", "lang/en.js")


def shell_version() -> str:
    h = hashlib.sha256()
    for name in _SHELL_FILES:
        p = STATIC_DIR / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


class Utf8JSON(JSONResponse):
    """JSON 一律声明 `charset=utf-8`。

    RFC 8259 说 JSON 默认就是 UTF-8，浏览器也这么认，所以不写也能用。
    但这个接口的内容**大部分是中文**（任务名、孩子写的一句话、伙伴的名字），
    而「导出 JSON」那条链接是给人下载下来看的——存成文件之后，
    中文系统上的记事本、Excel、某些编辑器会按本地编码（GBK）去猜，然后满屏乱码。
    多写这一句，下游就不用猜。
    """
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="KidsArtQuest", version=__version__, default_response_class=Utf8JSON)
# 接口全部挂在一个 router 上，文件末尾同时挂到 `/api/v1` 和 `/api`：
# app 上架之后，孩子手机上的旧版本会一直调着它发布那天的接口，版本号得**先于** 1.0 存在，
# 不然等要改的时候就得同时伺候两套没名字的接口。网页版和 app 都调 `/api/v1`；
# 不带版本号的 `/api` 是「当前版本」的别名，给 curl 和旧书签用。
api = APIRouter()
# iOS 壳从 `artquest://app` 发请求（外壳打在 app 包里，不是从服务器载入的），
# 这是跨源；`Authorization` 头要在预检里点名放行。
# 文本按 gzip 压过再出门。装在这儿而不是 Caddy 里，是因为那台机器上的 Caddyfile 是 root 的、
# 没有免密 sudo，改不动；Caddy 反代会把 Content-Encoding 原样透传。
# 实测原来全是裸传：app.js 234 KB、style.css 134 KB、/quests 102 KB、index.html 38 KB，
# 加起来占冷启动的大头。压完 /quests 9.6 KB、index.html 11.9 KB。
# 图片、字体、视频由 GZipMiddleware 自己的 exclude_content_types 跳过，不用管。
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(CORSMiddleware, allow_origins=cfg.CORS_ORIGINS,
                   allow_methods=["GET", "POST", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type"], max_age=600)
store = SessionStore()
accounts = AccountStore()
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# `before.png` / `after.png` / `final.png` are *phases*, not file names: since
# schema 3 a session stores one artwork plus, when a revision happened, the
# pre-feedback checkpoint. This route resolves a phase against whichever layout
# the session was written in, so every existing URL keeps working. Registered
# before the mount, which still serves everything else (reference/, checkpoints/).
@app.get("/files/{sid}/{phase}.png")
def phase_image(sid: str, phase: str):
    if phase not in ("before", "after", "final"):
        raise HTTPException(404, "not found")
    try:
        png = store.read_image(sid, phase)
    except KeyError:
        raise HTTPException(404, "session not found")
    if png is None:
        raise HTTPException(404, "not found")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-cache"})


app.mount("/files", StaticFiles(directory=SESSIONS_DIR), name="files")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def revalidate_the_app_shell(request, call_next):
    """外壳一律带 `no-cache`。

    没有这个头，`StaticFiles` 什么缓存指令都不发，浏览器就按**启发式**自己决定
    存多久——于是改完 CSS 之后，客户端可能拿到「新的 HTML 配旧的 CSS」，
    按钮画出来了却没有样式也没有事件，看起来就是坏的。这不是理论：
    iPad 上真碰到了一次。

    `no-cache` 不是「不缓存」，是「每次都回来问一句」。文件没变就是一个 304，
    几十字节；`StaticFiles` 本来就在发 ETag 和 Last-Modified，白用。
    这条只管外壳（`/static` 和首页），孩子的画（`/files`）另有自己的头。
    """
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/teacher", "/teacher/") or path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


def _quest_for_engines(meta: Dict[str, Any]) -> Dict[str, Any]:
    """评分 / 反馈 / 陪伴引擎看到的任务：按会话语言翻好，再带上 `ui`（simple 时话要短）。
    是一份拷贝，引擎只读。"""
    quest = i18n.quest_for(QUESTS_BY_ID[meta["quest_id"]], meta.get("lang", "zh"))
    return {**quest, "ui": (meta.get("condition") or {}).get("ui", "full")}


def _session_or_404(sid: str) -> Dict[str, Any]:
    try:
        return store.load(sid)
    except KeyError:
        raise HTTPException(404, "session not found")


def _ingest(sid: str, events: List[DrawEvent], strokes: List[Stroke]) -> Dict[str, Any]:
    """Append a client batch to the append-only logs (idempotent by seq)."""
    out = {}
    if events:
        out["events"] = store.append_client(sid, "events", [e.record() for e in events])
    if strokes:
        out["strokes"] = store.append_client(sid, "strokes", [s.model_dump() for s in strokes])
    return out


def _reference_available(sid: str, meta: Dict[str, Any]) -> Optional[bool]:
    """None when the task had no reference; False when it had one and it is gone."""
    if (meta.get("task") or {}).get("stimulus_kind") != "reference":
        return None
    return bool((meta.get("task") or {}).get("reference_file"))


def _run_qc(sid: str, pending: int = 0) -> Dict[str, Any]:
    meta = store.load(sid)
    try:
        # rebuild the artwork from the logs and hold it against what was saved
        replay = check_final(store.dir(sid))
    except Exception:
        log.exception("reconstruction failed for %s", sid)
        replay = None
    result = qc_check(
        meta,
        strokes=store._strokes_summary(sid),
        events=store.log(sid, "events").count(),
        known_task=meta.get("quest_id") in QUESTS_BY_ID,
        has_final_image=(store.dir(sid) / "final.png").exists(),
        pending_uploads=pending,
        replay=replay,
        condition_frozen=bool((store.condition_snapshot(sid) or {}).get("task_id")),
        reference_available=_reference_available(sid, meta),
        checksum=store.log_checksum(sid),
    )
    result["at"] = now_iso()
    store.save_quality(sid, result)          # into session.json, beside what it judges
    # `server_verified` means the logs agree with each other and with the artwork,
    # and nothing is still queued on the client — not merely "the child finished"
    verified = {"log_streams_agree", "replay_matches_final", "uploads_flushed"}
    if not (verified & set(result["failed"])):
        store.set_lifecycle(sid, "server_verified")
        store.finalize(sid)                  # nothing more is coming: compress the logs
    if not result["ok"]:
        log.warning("session %s failed QC: %s", sid, result["failed"])
    return result


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# -- 课后问卷：对 app 的看法 --------------------------------------------------
# 几道开放题，不打分。一条一个文件，放 data/opinions/。研究员令牌能列全部。
OPINION_KEYS = ("liked", "stuck", "feedback", "change", "more")
OPINIONS_DIR = SESSIONS_DIR.parent / "opinions"


@api.post("/opinions", status_code=201)
def post_opinion(body: Opinion):
    answers = {k: (body.answers.get(k) or "").strip()[:2000] for k in OPINION_KEYS if (body.answers.get(k) or "").strip()}
    if not answers:
        raise HTTPException(422, "什么都没写")
    OPINIONS_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"opinion_id": "op-" + secrets.token_hex(6), "ts": now_iso(), "answers": answers,
           "account_id": body.account_id, "anon_id": body.anon_id, "participant_id": body.participant_id, "lang": body.lang}
    (OPINIONS_DIR / f"{rec['ts'][:19].replace(':', '-')}-{rec['opinion_id']}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "opinion_id": rec["opinion_id"]}


@api.get("/opinions")
def list_opinions(request: Request):
    _require_admin(request)
    out = []
    if OPINIONS_DIR.exists():
        for f in sorted(OPINIONS_DIR.glob("*.json")):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            acc = accounts.load(rec.get("account_id") or "") if rec.get("account_id") else None
            rec["account_name"] = acc.get("name", "") if acc else ""
            out.append(rec)
    return {"opinions": out, "questions": list(OPINION_KEYS)}


# 隐私政策：一页静态 HTML，门口和「我的」里链到它；TestFlight / App Store 也要这个地址。
@app.get("/privacy")
def privacy_page():
    return FileResponse(STATIC_DIR / "privacy.html")


# 老师的入口：同一份 app，只是从这个路径打开时门口是老师的登录/注册。
# 不是第二个网站——同一份代码、同一个后端、同一批数据；路径归网站自己管，不用申请任何东西。
@app.get("/teacher")
@app.get("/teacher/")
def teacher_index():
    return FileResponse(STATIC_DIR / "index.html")


# Service Worker 必须从**根目录**发出来，它才管得了整个站（/static/sw.js 的作用域
# 只有 /static/）。文件本身仍然住在 static/ 里，这里只是换个路径端出去。
# no-cache 是故意的：浏览器拿旧的 sw.js 意味着旧的一整套外壳再也换不掉。
@app.get("/sw.js")
def service_worker():
    """把缓存版本号**当场换成外壳的哈希**再发出去。

    sw.js 里写的 `const VERSION = "dev"` 只是个占位。手写版本号这件事总会忘：
    改完 CSS 忘了 bump，装在主屏上的那份就抱着旧缓存不放，而人在 iPad 上
    根本看不出自己跑的是哪一版。现在文件一改哈希就变，SW 自己会去装新的。
    """
    src = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    src = re.sub(r'const VERSION = "[^"]*";', f'const VERSION = "{shell_version()}";', src, count=1)
    return Response(src, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


def art_available() -> Dict[str, List[str]]:
    """`static/art/` 里已经有的彩色插画：families/M1.png、badges/<徽章名>.png。

    有就用图，没有就退回代码画的线稿——所以美术可以一枚一枚地交，交一枚亮一枚，
    不用等 61 张齐了才换。清单在 docs/ART_LIST.md。
    """
    out: Dict[str, List[str]] = {}
    for kind in ("families", "badges", "map"):
        d = STATIC_DIR / "art" / kind
        out[kind] = sorted(p.stem for p in list(d.glob("*.png")) + list(d.glob("*.jpg"))) if d.is_dir() else []
    return out


@api.get("/config")
def config():
    scorer, fb = get_scorer(), get_feedback_engine()
    st = study_mod.load_study()
    return {
        "art": art_available(),
        "version": __version__,
        # 设备上跑的是哪一版外壳。「我的 → 这台设备」里显示它，
        # 这样在 iPad 上一眼就看得出更新到没有，不用靠猜。
        "shell": shell_version(),
        "schema_version": SCHEMA_VERSION,
        "snapshot_interval_sec": SNAPSHOT_INTERVAL_SEC,
        "scorer": scorer.name,
        "feedback": fb.name,
        "claude_available": claude_available(),
        "dimensions": DIMENSIONS,
        "scale_max": SCALE_MAX,
        "emotions": EMOTIONS,
        # the *resolved* default (study.json applies even outside Study Mode),
        # not the hardcoded one — otherwise the client believes a condition the
        # server is not running
        "default_condition": study_mod.resolve_condition(),
        "history_modes": list(HISTORY_MODES),
        "hardest_parts": [{"key": k, "label": v} for k, v in HARDEST_PARTS_SHOWN],
        "process_labels": list(PROCESS_LABELS),
        "study": {"active": st["active"], "study_id": st["study_id"], "order": st["order"]},
    }


@api.get("/families")
def get_families(request: Request):
    """Mission families — what the child picks from; a form is assigned below."""
    return i18n.families_for(task_families(), i18n.pick_lang(request))


# 孩子的界面真正读得到的字段。其余（rubric_summary / applicable_dims / process_targets /
# research_goal / prompt_style / form_id / phases / stimulus_placeholder / enabled /
# category / family_slug / anchor / version）是研究员元数据，app.js 里一处都没用到，
# 却占了这个接口一半的体积 —— 冷启动时它是最大的一笔，所以默认不发，
# 研究员用 `?full=1` 拿完整的那份（导出、protocol 工具都走它）。
# 2026-10-03 第一版把旧题（legacy）另裁成 9 个字段，结果破了一条契约：
# 「开放创作任务取的是每个研究字段的**宽松取值**（reference/time_limit_sec/allowed_tools 为
# null），这是合法条件取值而不是缺字段」—— 字段整个消失，和「缺字段」就分不开了
# （tests/test_research.py::test_open_task_gets_permissive_condition_values 抓到的）。
# 所以现在**所有任务一个字段表**，只去掉前端一处都读不到的那些研究员元数据。
QUEST_FIELDS_APP = (
    "id", "task_id", "family", "family_name", "type", "title", "instruction", "prompt", "hint",
    "icon", "color", "difficulty", "time_limit_sec", "allowed_tools",
    "stimulus", "reference", "condition", "rubric", "focus_dims", "tiers", "legacy", "lang",
)


def _slim(q: Dict[str, Any]) -> Dict[str, Any]:
    return {k: q[k] for k in QUEST_FIELDS_APP if k in q}


@api.get("/quests")
def quests(request: Request, full: int = 0):
    """英文界面拿英文题目；id、条件、刺激材料一样，只有给孩子看的字不同。

    默认只发孩子界面用得到的字段（`full=1` 发全部，给研究员和导出用）。
    """
    lang = i18n.pick_lang(request)
    rows = [i18n.quest_for(q, lang) for q in QUESTS]
    return rows if full else [_slim(q) for q in rows]


# -- study mode ------------------------------------------------------------
@api.get("/study")
def study_config():
    return study_mod.load_study()


@api.post("/study/assign")
def study_assign(body: StudyAssign):
    """Register a participant code and hand back their counterbalanced order."""
    return study_mod.assign(body.participant_id, body.anon_id, body.group)


# -- 账号 ------------------------------------------------------------------
# 只解决一件事：让画跟着**人**走。`anon_id` 是一台设备，孩子在 iPad 上画、
# 想在 iPhone 上看的时候它就失效了。设计取舍全部写在 accounts.py 开头。
def _account_error(e: AccountError) -> HTTPException:
    code = {"name_taken": 409, "device_taken": 409, "no_session": 401,
            "bad_credentials": 401, "locked": 429}.get(e.code, 400)
    return HTTPException(code, e.message)


def _scope(account_id: str = "") -> Dict[str, Any]:
    """一个账号在列表接口里的取景框：它自己 + 它认领过的设备。

    **认不出来的 account_id 原样带下去**，不要抹成空的：抹空了这一层筛选就整个消失，
    一个乱填的账号 id 会让「我的」接口退回研究员那份全量视图。认不出来的 id
    匹配不到任何作品，这才是它该有的结果。
    """
    acc = accounts.load(account_id) if account_id else None
    return {"account_id": account_id, "device_windows": accounts.device_windows(acc) if acc else {}}


# -- 谁在说话 ------------------------------------------------------------------
# 网页版一直靠「局域网 + SSH 隧道」这个信任假设兜着，应用层没有一处校验身份。
# app 直接调公网上的 API，每个请求都得自己证明是谁。三种身份，三条规矩：
#
#   * 研究员：`Authorization: Bearer <ARTQUEST_ADMIN_TOKEN>` —— 全量列表、打分、标注、策展。
#     没设这个环境变量这些接口就是关着的，不是开着的。
#   * 账号：  `Authorization: Bearer <登录令牌>` —— 凡是把 `account_id` 当筛选或归属参数
#     的地方，说自己是谁就得拿那个账号的令牌。以前 account_id 谁传谁生效。
#   * 设备：  只带 `anon_id` / 只知道 `session_id` —— 和以前一样。它们是猜不到的随机串，
#     相当于「不可猜的分享链接」，这个尺度可接受；要命的从来是全量列表把它们一次发光。
#
# 令牌走请求头不走查询串：URL 会原样进 Caddy 的 access log。
def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h[:7].lower() == "bearer " else ""


def _is_admin(request: Request) -> bool:
    tok = cfg.ADMIN_TOKEN
    return bool(tok) and secrets.compare_digest(_bearer(request), tok)


def _require_admin(request: Request) -> None:
    if _is_admin(request):
        return
    if not cfg.ADMIN_TOKEN:
        raise HTTPException(401, "研究员接口关着：服务器没设 ARTQUEST_ADMIN_TOKEN")
    raise HTTPException(401, "这个接口只给研究员：Authorization: Bearer <ARTQUEST_ADMIN_TOKEN>")


def _token(request: Request, legacy: str = "") -> str:
    """账号令牌：请求头优先；老客户端还放在 body / 查询串里的也认。"""
    return _bearer(request) or legacy


def _require_account(request: Request, legacy: str = "") -> Dict[str, Any]:
    try:
        return accounts.require(_token(request, legacy))
    except AccountError as e:
        raise _account_error(e)


def _check_owner(request: Request, account_id: str) -> None:
    """说自己是某个账号，就得拿那个账号的令牌。研究员可以替任何人问。

    401 和 403 分开：令牌本身不认（过期、别处退掉了）是 401，前端据此登出；
    令牌是好的但不是这个账号是 403——那是缓存里残留的别人的 account_id，不该把人踢下线。
    """
    if not account_id or _is_admin(request):
        return
    acc = accounts.by_token(_bearer(request))
    if not acc:
        raise HTTPException(401, "登录已经过期，再登一次吧")
    if acc["account_id"] != account_id:
        raise HTTPException(403, "这不是你的账号")


@api.post("/accounts/register", status_code=201)
def account_register(body: Register):
    if body.role == "teacher":
        code = cfg.teacher_code()
        if not code:
            raise HTTPException(403, "这台服务器没开放老师注册")
        if not secrets.compare_digest(body.teacher_code or "", code):
            raise HTTPException(403, "邀请码不对")
    try:
        return accounts.register(body.name, body.pin, anon_id=body.anon_id, buddy_name=body.buddy_name,
                                 age=body.age, role=body.role)
    except AccountError as e:
        raise _account_error(e)


@api.post("/accounts/login")
def account_login(body: Login):
    try:
        return accounts.login(body.name, body.pin, anon_id=body.anon_id)
    except AccountError as e:
        raise _account_error(e)


@api.post("/accounts/reset")
def account_reset(body: ResetPin, request: Request):
    """忘了暗号。孩子在自己登录过的设备上可以直接改；老师带研究员令牌可以替任何人改。
    403 = 这台设备没登录过这个账号（不是「名字不存在」，那是 401）。"""
    try:
        return accounts.reset_pin(body.name, body.pin, anon_id=body.anon_id, by_admin=_is_admin(request))
    except AccountError as e:
        if e.code == "not_your_device":
            raise HTTPException(403, e.message)
        raise _account_error(e)


@api.get("/accounts/me")
def account_me(request: Request, token: str = "", anon_id: str = ""):
    """当前登录的是谁，外加「这台设备上还有几张没归属的画」——
    那个数字是「收进我的」按钮存在的全部理由，所以在这儿一起给。
    令牌从 `Authorization: Bearer` 来；`?token=` 只是给旧客户端留的。"""
    acc = _require_account(request, token)
    pub = accounts.public(acc)
    claimed = anon_id in accounts.device_windows(acc)
    return {"account": pub, "unclaimed_here": 0 if claimed else len(store.unowned(anon_id)),
            "claimed_here": claimed}


@api.post("/accounts/claim")
def account_claim(body: ClaimDevice, request: Request):
    """把这台设备上以前画的收进自己名下。**不改任何 session**：
    记的是「这个账号认领过这台设备，截止到此刻」，旧数据一个字节不动。"""
    acc = _require_account(request, body.token)
    try:
        pub = accounts.claim_device(acc["account_id"], body.anon_id)
    except AccountError as e:
        raise _account_error(e)
    return {"ok": True, "account": pub, "claimed": len(store.unowned(body.anon_id))}


@api.post("/accounts/profile")
def account_profile(body: ProfileUpdate, request: Request):
    """伙伴的名字跟着账号走，换台设备它还叫原来那个名字。"""
    acc = _require_account(request, body.token)
    try:
        return {"ok": True, "account": accounts.set_buddy_name(acc["account_id"], body.buddy_name)}
    except AccountError as e:
        raise _account_error(e)


@api.post("/accounts/logout")
def account_logout(body: TokenOnly, request: Request):
    """只退这一台设备。别处仍然登录着——共用 iPad 上退出的那个孩子，
    不该把自己手机上的登录也一起弄掉。"""
    accounts.logout(_token(request, body.token))
    return {"ok": True}


# -- sessions --------------------------------------------------------------
# -- 教师端 ----------------------------------------------------------------
# 老师登录进来就是打分：最终图九维 + 评语，过程图各一句短评。数据是服务器上全部画完的作品。
# 凭证：老师账号的令牌（role=teacher），或研究员令牌。学生的令牌 403。
def _require_teacher(request: Request) -> Dict[str, str]:
    if _is_admin(request):
        return {"rater_id": "admin", "name": "研究员"}
    acc = accounts.by_token(_bearer(request))
    if not acc:
        raise HTTPException(401, "登录已经过期，再登一次吧")
    if acc.get("role") != "teacher":
        raise HTTPException(403, "这个界面只给老师")
    return {"rater_id": acc["account_id"], "name": acc.get("name", "")}


def _student_name(meta: Dict[str, Any]) -> str:
    p = meta.get("participant") or {}
    if isinstance(p, dict):
        acc = accounts.load(p.get("account_id") or "") if p.get("account_id") else None
        if acc:
            return acc.get("name", "")
        if p.get("participant_id"):
            return p["participant_id"]
        return "匿名 " + (p.get("anon_id") or "")[-4:]
    return str(p or "")


def _teacher_ratings(sid: str) -> List[Dict[str, Any]]:
    return [r for r in store.labels(sid, "rating") if r.get("source") == "teacher"]


def _session_images(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """老师要看的图，按时间顺序：过程快照、（改过的话）改之前那张、最终图。
    过程图只要一句短评；最终图要九维 + 评语。"""
    sid = sid_of(meta)
    out = []
    # 快照每分钟一张，一张画十几张，老师看不过来也不必看：只抽三张——开头、中间、快结束。
    # 全部快照照存在服务器上，研究分析时都在；这只是老师界面上的抽样。
    snaps = list(meta.get("snapshots") or [])
    if len(snaps) > 3:
        snaps = [snaps[0], snaps[len(snaps) // 2], snaps[-1]]
    for s in snaps:
        out.append({"key": s["file"], "url": f"/files/{sid}/{s['file']}", "kind": "snapshot", "elapsed_ms": s.get("elapsed_ms")})
    if meta.get("revised"):
        out.append({"key": "before", "url": f"/files/{sid}/before.png", "kind": "before",
                    "elapsed_ms": (meta.get("before") or {}).get("elapsed_ms")})
    out.append({"key": "final", "url": f"/files/{sid}/final.png", "kind": "final",
                "elapsed_ms": (meta.get("times") or {}).get("duration_ms")})
    return out


@api.get("/teacher/rubric")
def teacher_rubric(request: Request):
    """老师打分时的参考：KidsArtBench 九维五档的原文与中译、1,046 幅作品的专家打分分布、评语示范。
    内容是静态的（scoring/levels.py），但只给老师——它是研究材料，不进学生界面。"""
    _require_teacher(request)
    return rubric_payload()


def _done_sessions() -> List[Dict[str, Any]]:
    out = []
    for row in store.list():
        if row.get("status") != "done":
            continue
        try:
            out.append(store.load(row["session_id"]))
        except KeyError:
            continue
    return out


@api.get("/teacher/sessions")
def teacher_sessions(request: Request, status: str = "all"):
    """老师的池子。todo = 没评满 K 次、我也没评过的（评得少的在前）；done = 我评过的。
    研究员看全部，每行带 n_ratings / full。评分数据一条不删，评满只是从待评里消失。"""
    me = _require_teacher(request)
    k = teacher_pool.ratings_per_work()
    admin = me["rater_id"] == "admin"
    rows = []
    n_total = 0
    for meta in _done_sessions():
        n_total += 1
        sid = sid_of(meta)
        ratings = _teacher_ratings(sid)
        n_ratings = len({r.get("rater_id") for r in ratings})
        graded = any(r.get("rater_id") == me["rater_id"] for r in ratings)
        full = n_ratings >= k
        if not admin:
            if status == "todo" and (graded or full):
                continue
            if status == "done" and not graded:
                continue
            if status == "all" and not graded and full:
                continue
        task = meta.get("task") or {}
        rows.append({
            "session_id": sid, "created_at": meta.get("created_at"),
            "task_id": task.get("task_id") or meta.get("quest_id"), "task_title": task.get("title") or meta.get("quest_id"),
            "student": _student_name(meta), "lang": meta.get("lang", "zh"),
            "image": f"/files/{sid}/final.png", "n_snapshots": len(meta.get("snapshots") or []),
            "revised": bool(meta.get("revised")), "duration_ms": (meta.get("times") or {}).get("duration_ms"),
            "graded_by_me": graded, "n_graders": n_ratings, "n_ratings": n_ratings, "full": full,
        })
    # 待评：评得少的在前、老的在前，每件尽快凑满；评过的：新的在前
    todo = sorted((r for r in rows if not r["graded_by_me"]), key=lambda r: (r["n_ratings"], r.get("created_at") or ""))
    done = sorted((r for r in rows if r["graded_by_me"]), key=lambda r: r.get("created_at") or "", reverse=True)
    rows = todo + done
    return {"me": me, "sessions": rows, "ratings_per_work": k, "n_total": n_total,
            "n_todo": sum(1 for r in rows if not r["graded_by_me"]) if status == "all" else None}


@api.get("/teacher/progress")
def teacher_progress(request: Request):
    """研究员看进度：每件评了几次、评满了几件；每位老师评了几件。"""
    _require_admin(request)
    k = teacher_pool.ratings_per_work()
    teachers = {a["account_id"]: {"account_id": a["account_id"], "name": a.get("name", ""), "n_graded": 0} for a in accounts.teachers()}
    works = []
    for meta in _done_sessions():
        sid = sid_of(meta)
        raters = {r.get("rater_id") for r in _teacher_ratings(sid)}
        for rid in raters:
            if rid in teachers:
                teachers[rid]["n_graded"] += 1
        works.append({"session_id": sid, "n_ratings": len(raters), "full": len(raters) >= k})
    return {"ratings_per_work": k, "n_works": len(works), "n_full": sum(1 for w in works if w["full"]),
            "teachers": list(teachers.values()), "works": works}


@api.post("/teacher/progress")
def teacher_progress_update(body: TeacherPoolUpdate, request: Request):
    """研究员改 K（每件要几份评分）。改小了，已经够数的作品立刻从待评里消失；改大了，回来。"""
    _require_admin(request)
    teacher_pool.set_ratings_per_work(body.ratings_per_work)
    return teacher_progress(request)


@api.get("/teacher/sessions/{sid}")
def teacher_session(sid: str, request: Request):
    """一件作品的全部：图（过程 + 最终）、任务、心愿、我上次的评分。**不给模型的分**——老师不该被它带着走。"""
    me = _require_teacher(request)
    meta = _session_or_404(sid)
    task = meta.get("task") or {}
    mine = [r for r in _teacher_ratings(sid) if r.get("rater_id") == me["rater_id"]]
    last = mine[-1] if mine else None
    rubric = task.get("rubric") or {}
    return {
        "session_id": sid, "student": _student_name(meta), "created_at": meta.get("created_at"),
        "lang": meta.get("lang", "zh"),
        "task": {"task_id": task.get("task_id"), "title": task.get("title"), "instruction": task.get("instruction") or task.get("prompt"),
                 "family_name": task.get("family_name") or task.get("type")},
        "intent": meta.get("intent") or {},
        "duration_ms": (meta.get("times") or {}).get("duration_ms"),
        "images": _session_images(meta),
        "dimensions": [{"key": d["key"], "zh": d["zh"], "en": d["en"], "desc": d["desc"]} for d in DIMENSIONS],
        "not_applicable": list(rubric.get("not_applicable_dimensions") or []),
        "scale_max": SCALE_MAX,
        "my_rating": ({"dims": last.get("dims") or {}, "comment": last.get("note") or "",
                       "image_notes": last.get("image_notes") or {}, "at": last.get("ts")} if last else None),
        "n_graders": len({r.get("rater_id") for r in _teacher_ratings(sid)}),
    }


@api.post("/teacher/sessions/{sid}/grade")
def teacher_grade(sid: str, body: TeacherGrade, request: Request):
    """老师交卷。追加一条 rating（不覆盖别人的，也不覆盖自己上一次的——数据集要能报一致性）。"""
    me = _require_teacher(request)
    meta = _session_or_404(sid)
    if meta.get("status") != "done":
        raise HTTPException(409, "这张还没画完")
    rubric = (meta.get("task") or {}).get("rubric")
    bad = check_rating(body.dims, rubric)
    if bad:
        raise HTTPException(422, f"这个任务无法考察这些维度，不能打分：{bad}")
    if not body.dims and not body.comment and not body.image_notes:
        raise HTTPException(422, "什么都没写")
    # 过程图至少写一条（有过程图才要求）：写在哪一张老师自己挑。写了才算真看过过程，研究也留一个人工的过程判断。
    process_keys = {im["key"] for im in _session_images(meta) if im["kind"] != "final"}
    if process_keys and not (set(body.image_notes) & process_keys):
        raise HTTPException(422, "过程图至少写一条短评")
    rec = store.add_rating(sid, {
        "source": "teacher", "rater_id": me["rater_id"], "rater_name": me["name"],
        "phase": "after" if meta.get("revised") else "before",
        "overall": None, "dims": body.dims, "note": body.comment, "image_notes": body.image_notes,
        "t_ms": body.t_ms, "featured": False, "rubric_version": (rubric or {}).get("version"),
    })
    store.add_server_event(sid, "RATING_ADDED", body.t_ms,
                           {"rating_id": rec["rating_id"], "source": "teacher", "rater_id": me["rater_id"],
                            "overall": None, "n_dims": len(body.dims), "n_image_notes": len(body.image_notes)})
    return {"ok": True, "rating_id": rec["rating_id"]}


@api.get("/sessions")
def list_sessions(request: Request, participant_id: str = "", anon_id: str = "", account_id: str = ""):
    """带上身份 = 这个孩子自己的那些（app 永远带）；不带任何身份 = 研究员的全量视图，
    要研究员令牌——以前这一条不带参数就把全服的 session id 一次发光，
    而 id 是 `/files/` 和 `/api/sessions/{id}` 唯一的门。"""
    if not (participant_id or anon_id or account_id):
        _require_admin(request)
    _check_owner(request, account_id)
    return store.list(participant_id=participant_id, anon_id=anon_id, **_scope(account_id))


# 删掉自己的一张画。**真删**，不是标记——隐私政策里写的「删除」就是这个意思。
#
# `tools/withdraw.py` 里写过一条相反的设计决定：撤回故意只做成 CLI，因为「一台能通过
# 网络删孩子作品的研究服务器比不能删的更糟」。那条针对的是**整个被试的批量撤回**，
# 一次管理动作。孩子在画廊里删掉自己刚画的一张是另一回事：范围是一件、主体是本人、
# 是产品本来就该有的东西。护栏按那条顾虑来设：
#
#   · 一次一张，没有批量接口
#   · 只能删**归自己**的（`storage.belongs_to` 那一份实现，说自己是某账号就得拿它的令牌）
#   · 不是自己的和不存在的回同一个 404 —— 403 等于告诉陌生人「这张画在」
#   · 留一张**不含任何内容**的回执：谁、什么时候、删了哪一条、里面有多少笔。
#     没有图、没有心愿、没有评语。研究员据此知道 protocol 上空了一格。
DELETIONS_DIR = SESSIONS_DIR.parent / "deletions"


def _owner_windows(account_id: str) -> Dict[str, str]:
    acc = accounts.load(account_id) if account_id else None
    return accounts.device_windows(acc) if acc else {}


@api.delete("/sessions/{sid}")
def delete_session(sid: str, request: Request, participant_id: str = "",
                   anon_id: str = "", account_id: str = ""):
    _check_owner(request, account_id)
    try:
        meta = store.load(sid)
    except KeyError:
        raise HTTPException(404, "没有这张画")
    mine = storage_belongs_to(meta, participant_id=participant_id, anon_id=anon_id,
                              account_id=account_id, windows=_owner_windows(account_id))
    if not (mine or _is_admin(request)):
        raise HTTPException(404, "没有这张画")
    rec = {
        "session_id": sid, "deleted_at": now_iso(), "by": "admin" if not mine else "owner",
        "account_id": (meta.get("participant") or {}).get("account_id", "") if isinstance(meta.get("participant"), dict) else "",
        "anon_id": (meta.get("participant") or {}).get("anon_id", "") if isinstance(meta.get("participant"), dict) else "",
        "participant_id": (meta.get("participant") or {}).get("participant_id", "") if isinstance(meta.get("participant"), dict) else "",
        "task_id": (meta.get("task") or {}).get("task_id") or meta.get("quest_id", ""),
        "created_at": meta.get("created_at", ""), "status": meta.get("status", ""),
        "n_strokes": len(store.strokes(sid) or []) if meta.get("status") else 0,
        "n_snapshots": len(meta.get("snapshots") or []),
    }
    store.delete(sid)
    DELETIONS_DIR.mkdir(parents=True, exist_ok=True)
    (DELETIONS_DIR / f"{rec['deleted_at'][:19].replace(':', '-')}-{sid}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "session_id": sid}


@api.get("/deletions")
def list_deletions(request: Request):
    """研究员看哪些作品被本人删掉了。回执里没有内容，只有「哪一条、什么时候、多少笔」。"""
    _require_admin(request)
    out = []
    if DELETIONS_DIR.exists():
        for f in sorted(DELETIONS_DIR.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return {"deletions": out}


@api.get("/sessions/{sid}")
def get_session(sid: str):
    try:
        return store.load_full(sid)
    except KeyError:
        raise HTTPException(404, "session not found")


@api.get("/sessions/{sid}/strokes")
def get_strokes(sid: str):
    """Raw stroke log — enough on its own to replay the whole drawing."""
    _session_or_404(sid)
    return store.log(sid, "strokes").read()


def _personalize(sid: str, quest: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    """Build this child's representation and let the arm decide, before they draw.

    The representation is rebuilt from the logs every time (so it always
    reflects the current builder) but the copy used here is frozen into the
    session — `history.build(before=...)` with this session's timestamp
    reproduces the same input later.
    """
    cond = meta.get("condition") or {}
    mode = cond.get("history_mode", "none")
    who = meta.get("participant") or {}
    rep = None
    if mode != "none":
        sc = _scope(who.get("account_id", ""))
        try:
            rep = history_mod.build(who.get("participant_id", ""), who.get("anon_id", ""),
                                    account_id=sc["account_id"], windows=sc["device_windows"],
                                    before=meta.get("created_at") or "")
        except Exception:
            log.exception("representation build failed for %s", sid)
    try:
        decision = get_personalizer(mode).prepare(quest, rep)
    except Exception as e:                      # an arm must never lose the session
        log.exception("personalizer failed")
        decision = {"requested_mode": mode, "backend": "error", "available": False,
                    "note": str(e), "history_used": {}, "shown": [], "prediction": {}}
    # the whole representation goes in: a decision is only reproducible next to
    # the state it was made from
    decision["representation"] = rep
    return store.save_personalization(sid, decision)


@api.post("/tickets", status_code=201)
def issue_tickets(body: IssueTickets, request: Request):
    """预发几张票，留着离线用。

    一张票 = 服务端生成的 `session_id` + **此刻冻结好的 condition**，目录当场占住。
    孩子离线开始创作就是花掉一张，不发任何请求；重新联网时队列把创建和笔画一起补上。

    为什么不让客户端自己发 id：那会一次性毁掉三样东西——id 的可信性（它是后面
    每张表的外键）、条件冻结（孩子究竟跑在哪条实验臂上），以及重放时分不清
    「这个 session 还没建」和「这个 session 根本不存在」。票据把服务端的决定
    **提前**而不是拿掉。
    """
    _check_owner(request, body.participant.account_id)
    n = max(1, min(20, body.n))
    st = body.study.model_dump()
    quest_ids = body.quest_ids[:n]
    out = []
    for i in range(n):
        qid = quest_ids[i] if i < len(quest_ids) else ""
        quest = QUESTS_BY_ID.get(qid) if qid else None
        if qid and quest is None:
            raise HTTPException(400, f"unknown quest {qid}")
        condition = study_mod.resolve_condition(None, st.get("group", ""))
        if quest and quest.get("time_limit_sec") and not condition.get("time_limit_sec"):
            condition["time_limit_sec"] = quest["time_limit_sec"]
        t = store.issue(condition=condition, participant=body.participant.model_dump(),
                        study=st, quest_id=qid)
        out.append({"session_id": t["session_id"], "issued_at": t["issued_at"],
                    "condition": t["condition"], "quest_id": qid})
    return {"tickets": out}


@api.post("/sessions", status_code=201)
def create_session(body: CreateSession, request: Request):
    quest = QUESTS_BY_ID.get(body.task())
    if quest is None:
        raise HTTPException(400, "unknown quest")
    who = body.participant_dict()
    if who.get("account_id"):
        # 说这幅画是某个账号的，就得拿那个账号的令牌——除了花票：票是联网时拿着令牌
        # 领的，账号那会儿就核过了；离线画完重放时孩子可能已经退出登录，不能让画丢在半路。
        ticket = None
        if body.session_id:
            try:
                ticket = store.load(body.session_id)
            except KeyError:
                ticket = None
        if not (ticket and (ticket.get("participant") or {}).get("account_id") == who["account_id"]):
            _check_owner(request, who["account_id"])
    st = body.study.model_dump()
    condition = study_mod.resolve_condition(body.condition, st.get("group", ""))
    if quest.get("time_limit_sec") and not condition.get("time_limit_sec"):
        condition["time_limit_sec"] = quest["time_limit_sec"]
    # 界面语言此刻冻进 session：之后评分、反馈、陪伴都按它，task 快照记的也是孩子看到的那一版
    lang = i18n.pick_lang(request)
    quest = i18n.quest_for(quest, lang)
    try:
        meta = store.create(
            quest, body.intent.model_dump(),
            participant=body.participant_dict(), condition=condition,
            device=body.device.model_dump(), study=st, canvas=body.canvas.model_dump(),
            sid=body.session_id or None, lang=lang,
        )
    except KeyError:
        # 带了一个从没发出去过的票号。不当场给它建一个——那正是「客户端自己发 id」
        # 的后门，会把 id 的可信性从后门放回来。
        raise HTTPException(404, "unknown ticket")
    # 重放一张已经用过的票：原样返回，不重跑下面那串「冻条件、拷参考图、写开场事件」
    if meta.get("lifecycle") != "recording" or meta.get("times", {}).get("started_at"):
        return {"session_id": sid_of(meta), "session": store.load(sid_of(meta)),
                "personalization": {}, "replayed": True}
    condition = meta.get("condition") or condition      # 票上冻的那份才算数
    store.mark_started(sid_of(meta))
    # what this child actually saw, frozen before anything else happens
    store.save_condition(sid_of(meta), condition_snapshot(
        quest, app_version=__version__, condition=condition,
        protocol={"study_id": st.get("study_id", ""), "group": st.get("group", ""),
                  "protocol_id": st.get("protocol_id", ""),
                  "sequence_id": st.get("sequence_id", "")},
        task_order=st.get("order_index")))
    ref_file = store.copy_reference(sid_of(meta), quest)
    if ref_file:
        store.update_task(sid_of(meta), reference_file=ref_file)
    store.add_server_event(sid_of(meta), ev.TASK_SHOW, 0, {
        "task_id": quest["id"], "family": quest.get("family", ""),
        "form_id": quest.get("form_id", ""), "prompt_style": quest.get("prompt_style", ""),
        "task_version": quest.get("version", "")})
    store.add_server_event(sid_of(meta), "SESSION_START", 0, {
        "task_id": quest["id"], "condition": condition, "study_id": st.get("study_id", "")})
    personalization = _personalize(sid_of(meta), quest, meta)
    if personalization.get("shown"):
        store.add_server_event(sid_of(meta), "HISTORY_SHOWN", 0, {
            "backend": personalization.get("backend"),
            "requested_mode": personalization.get("requested_mode"),
            "n_lines": len(personalization["shown"]),
            "n_prior_tasks": (personalization.get("history_used") or {}).get("n_tasks", 0)})
    return {"session_id": sid_of(meta), "session": store.load(sid_of(meta)),
            # the client only needs what to show; the representation stays server-side
            "personalization": {k: personalization.get(k) for k in
                                ("requested_mode", "backend", "available", "shown", "history_used")}}


@api.post("/sessions/{sid}/log")
def ingest_log(sid: str, body: LogBatch):
    """Batched, idempotent ingest of buffered strokes and events.

    The client writes to local storage first and flushes here; re-sending a
    batch after a dropped connection cannot duplicate rows.
    """
    _session_or_404(sid)
    out = _ingest(sid, body.events, body.strokes)
    if body.pending == 0:
        store.set_lifecycle(sid, "uploaded")
    return {"ok": True, "streams": out}


@api.post("/sessions/{sid}/assist")
def assist(sid: str, body: AssistIn):
    """孩子画到一半，点开那扇模糊的窗。

    `dialogue_mode` 是冻结在 session 上的条件，所以它必须**真的决定点什么**——
    `feedback_source` 曾经被声明了却没人执行，元数据说「没有反馈」而孩子照样
    收到了，那是两头不落好。对照组在这里直接 403，前端连窗都不画。

    这一层只鼓励和发问，不评价质量；评价在交卷之后的 `/submit`。
    理由见 `artquest/assist/__init__.py` 的模块注释。
    """
    meta = _session_or_404(sid)
    mode = (meta.get("condition") or {}).get("dialogue_mode", "on_demand")
    if mode == "none":
        raise HTTPException(403, "dialogue_mode is none for this session")
    try:
        png = decode_data_url(body.image)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _ingest(sid, body.events, [])
    quest = _quest_for_engines(meta)
    try:
        out = get_assist_engine().assist(png, quest, meta.get("intent") or {}, nth=max(1, body.nth))
    except Exception as e:                      # 陪伴挂了绝不能挡住画画
        log.exception("assist failed")
        return {"text": i18n.say(meta.get("lang", "zh"), "我在这儿呢，接着画。", "I'm here. Keep going."),
                "backend": "error", "error": str(e)}
    return {"text": out["text"], "backend": out.get("backend", "")}


@api.post("/sessions/{sid}/snapshot")
def snapshot(sid: str, body: Snapshot):
    _session_or_404(sid)
    try:
        png = decode_data_url(body.image)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _ingest(sid, body.events, [])
    name = store.add_snapshot(sid, png, body.elapsed_ms)
    return {"ok": True, "file": name}


def _score_and_save(sid: str, phase: str, png: bytes, elapsed_ms: int) -> Dict[str, Any]:
    meta = store.load(sid)
    quest, intent = _quest_for_engines(meta), meta["intent"]
    store.save_phase_image(sid, phase, png)
    try:
        scores = get_scorer().score(png, quest, intent)
    except Exception as e:  # scoring must never lose the artwork
        log.exception("scoring failed")
        scores = {"backend": "error", "scale": [1, SCALE_MAX], "dims": {}, "summary": f"评分失败：{e}"}
    # N/A is not a low score: a dimension this task cannot elicit carries no number
    scores = apply_contract(scores, quest.get("rubric"))
    return {"file": f"{phase}.png", "elapsed_ms": elapsed_ms, "at": now_iso(), "scores": scores}


@api.post("/sessions/{sid}/submit")
def submit(sid: str, body: Submit):
    meta = _session_or_404(sid)
    try:
        png = decode_data_url(body.image)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _ingest(sid, body.events, body.strokes)
    quest, intent = _quest_for_engines(meta), meta["intent"]
    engine = get_feedback_engine()

    if body.phase == "before":
        if meta.get("before"):
            raise HTTPException(409, "before already submitted")
        record = _score_and_save(sid, "before", png, body.elapsed_ms)

        # `feedback_source` is a frozen condition, so it has to actually decide
        # something. It was declared and never enforced, which is the worst of
        # both: the metadata claims "no feedback" while the child gets some.
        source = (meta.get("condition") or {}).get("feedback_source", "ai")
        if source != "ai":
            # scores are still computed and stored — assessment continues, the
            # child is simply not shown an intervention this session
            meta = store.update(sid, before=record, feedback=None, status="submitted")
            return {"phase": "before", "scores": record["scores"], "feedback": None,
                    "feedback_source": source, "session": meta}

        try:
            fb = engine.feedback(png, quest, intent, record["scores"])
        except Exception as e:
            log.exception("feedback failed")
            fb = {"backend": "error", "text": f"反馈生成失败：{e}"}
        fb["at"] = now_iso()
        # structured record + the anchor that splits "before feedback" from "after"
        entry = store.add_feedback(sid, {
            "t_ms": body.elapsed_ms, "phase": "before", "source": "ai",
            "feedback_type": "formative", "backend": fb["backend"], "text": fb["text"],
            # provenance, so a later model-generated intervention is comparable
            "trigger": "submit", "model": CLAUDE_MODEL if fb["backend"] == "claude" else "",
            "prompt_version": PROMPT_VERSION})
        fb["feedback_id"] = entry["feedback_id"]
        fb["t_ms"] = body.elapsed_ms
        # `entry` *is* the FEEDBACK_SHOW event on the timeline — no second record
        meta = store.update(sid, before=record, feedback=fb, status="feedback")
        return {"phase": "before", "scores": record["scores"], "feedback": fb,
                "feedback_source": source, "session": meta}

    # phase == "after"
    if not meta.get("before"):
        raise HTTPException(409, "submit before first")
    if meta.get("after"):
        raise HTTPException(409, "after already submitted")
    record = _score_and_save(sid, "after", png, body.elapsed_ms)
    source = (meta.get("condition") or {}).get("feedback_source", "ai")
    cmp = None
    if source == "ai":
        before_png = store.read_image(sid, "before")
        try:
            cmp = engine.compare(before_png, png, meta["before"]["scores"], record["scores"], quest, intent)
        except Exception as e:
            log.exception("compare failed")
            cmp = {"backend": "error", "text": f"对比生成失败：{e}"}
        store.add_feedback(sid, {"t_ms": body.elapsed_ms, "phase": "after", "source": "ai",
                                 "feedback_type": "comparison", "backend": cmp["backend"],
                                 "text": cmp["text"], "trigger": "submit",
                                 "prompt_version": PROMPT_VERSION})
    store.add_server_event(sid, "SESSION_END", body.elapsed_ms, {"revised": True})
    store.update(sid, after=record, comparison=cmp, revised=True, status="done")
    store.mark_ended(sid, body.elapsed_ms)
    store.set_lifecycle(sid, "pending_upload" if body.pending else "completed_local")
    if not body.pending:
        store.set_lifecycle(sid, "uploaded")
    qc = _run_qc(sid, body.pending)
    return {"phase": "after", "scores": record["scores"], "comparison": cmp,
            "session": store.load_full(sid), "qc": qc}


@api.post("/sessions/{sid}/finalize")
def finalize(sid: str, body: Finalize):
    """Finish without revising: `after` is a copy of `before`."""
    meta = _session_or_404(sid)
    if not meta.get("before"):
        raise HTTPException(409, "submit before first")
    if meta.get("after"):
        return {"session": meta}
    _ingest(sid, body.events, body.strokes)
    # declining to revise is an outcome of *that* feedback, not an absence of data
    last_fb = meta.get("feedback") or {}
    store.add_server_event(sid, "REVISION_SKIPPED", body.elapsed_ms, {
        "feedback_id": last_fb.get("feedback_id"),
        "latency_ms": body.elapsed_ms - (last_fb.get("t_ms") or 0) if last_fb.get("feedback_id") else None})
    # No revision means no second artwork: `final.png` already is the work,
    # and copying it under a second name is a copy, not a measurement.
    record = dict(meta["before"], file="final.png", elapsed_ms=body.elapsed_ms, at=now_iso())
    store.add_server_event(sid, "SESSION_END", body.elapsed_ms, {"revised": False})
    store.update(sid, after=record, revised=False, status="done")
    store.mark_ended(sid, body.elapsed_ms)
    store.set_lifecycle(sid, "pending_upload" if body.pending else "completed_local")
    if not body.pending:
        store.set_lifecycle(sid, "uploaded")
    qc = _run_qc(sid, body.pending)
    return {"session": store.load_full(sid), "qc": qc}


@api.post("/sessions/{sid}/abandon")
def abandon(sid: str, body: Abandon):
    """The child backed out — wrong task, or they want to start over.

    Everything drawn so far is kept: changing your mind two minutes in is real
    process data, and deleting it would also mean a task_id could silently have
    two different meanings. The session is *marked*, not removed, and
    `status: abandoned` keeps it out of history, representations and QC noise.
    """
    meta = _session_or_404(sid)
    if meta.get("status") == "done":
        raise HTTPException(409, "session already finished")
    _ingest(sid, body.events, body.strokes)
    store.add_server_event(sid, ev.SESSION_ABANDONED, body.elapsed_ms,
                           {"reason": body.reason, "strokes": (meta.get("counts") or {}).get("strokes", 0)})
    store.update(sid, status="abandoned", abandoned_reason=body.reason)
    store.mark_ended(sid, body.elapsed_ms)
    return {"ok": True, "session_id": sid, "status": "abandoned"}


@api.post("/sessions/{sid}/questionnaire")
def questionnaire(sid: str, body: Questionnaire):
    _session_or_404(sid)
    answers = body.model_dump()
    rec = store.save_questionnaire(sid, {k: v for k, v in answers.items() if k != "t_ms"})
    store.add_server_event(sid, "QUESTIONNAIRE_SUBMITTED", body.t_ms,
                           {k: v for k, v in rec.items() if isinstance(v, int)})
    # the self-report is the label the pre-task prediction was written against
    scored = store.record_prediction_outcome(sid, rec)
    return {"ok": True, "questionnaire": rec,
            "prediction_error": (scored or {}).get("error")}


@api.post("/sessions/{sid}/feedback")
def add_feedback(sid: str, body: FeedbackIn, request: Request):
    _require_admin(request)
    """Record a teacher's or the child's own feedback next to the AI's.

    `target_region` is in canvas pixel space, the same coordinates strokes use,
    so `/revision` can answer whether the child then worked where it pointed.
    """
    _session_or_404(sid)
    rec = store.add_feedback(sid, body.model_dump())   # the record *is* the event
    return {"ok": True, "feedback": rec}


@api.post("/sessions/{sid}/rating")
def add_rating(sid: str, body: Rating, request: Request):
    _require_admin(request)
    """A teacher's / expert's rating of the artwork — a second rater, not the child."""
    meta = _session_or_404(sid)
    rubric = (meta.get("task") or {}).get("rubric")
    bad = check_rating(body.dims, rubric)
    if bad:
        raise HTTPException(422, f"这个任务无法考察这些维度，不能打分：{bad}")
    rec = store.add_rating(sid, dict(body.model_dump(), rubric_version=(rubric or {}).get("version")))
    store.add_server_event(sid, "RATING_ADDED", body.t_ms,
                           {"rating_id": rec["rating_id"], "source": body.source,
                            "rater_id": body.rater_id, "overall": body.overall,
                            "n_dims": len(body.dims)})
    featured = None
    if body.featured:
        # 老师挑中只是一个**提议**：作品先不展出，等本人答复
        featured = store.propose_featured(sid, by=body.rater_id, note=body.note)
    return {"ok": True, "rating": rec, "featured": featured}


@api.get("/participants/{pid}/featured")
def featured_pending(pid: str, request: Request, anon_id: str = "", account_id: str = ""):
    _check_owner(request, account_id)
    """这个孩子有哪几张被老师挑中、还等着他自己答复。"""
    sc = _scope(account_id)
    out = []
    for meta in history_mod.sessions_for(pid, anon_id, account_id=sc["account_id"],
                                         windows=sc["device_windows"]):
        rec = meta.get("featured") or {}
        if rec.get("state") != "pending":
            continue
        sid = sid_of(meta)
        quest = i18n.quest_for(QUESTS_BY_ID.get(meta.get("quest_id")) or {}, meta.get("lang", "zh"))
        out.append({"session_id": sid, "task_id": meta.get("quest_id"),
                    "title": quest.get("title") or meta.get("quest_id"),
                    "image": f"/files/{sid}/final.png",
                    "by": rec.get("by", ""), "note": rec.get("note", ""),
                    "proposed_at": rec.get("proposed_at")})
    return {"participant_id": pid, "pending": out}


@api.post("/sessions/{sid}/featured")
def answer_featured(sid: str, body: FeaturedAnswer):
    """孩子自己的答复。答应了才会挂到大家那面墙上；随时可以反悔。"""
    _session_or_404(sid)
    return {"ok": True, "featured": store.answer_featured(sid, body.accept)}


@api.get("/sessions/{sid}/revision")
def get_revision(sid: str):
    """Feedback → what the child did next, in time and (when targeted) in space.

    Derived from the logs on request, never stored: the relation improves when
    the analysis does.
    """
    _session_or_404(sid)
    return attribute_revision(store.dir(sid))


@api.post("/sessions/{sid}/annotation")
def add_annotation(sid: str, body: Annotation, request: Request):
    _require_admin(request)
    """An expert labelling a stretch of the replay (planning / revision / …)."""
    meta = _session_or_404(sid)
    duration = (meta.get("times") or {}).get("duration_ms")
    if duration and body.t_start_ms > duration:
        raise HTTPException(422, f"span starts after the session ended ({duration} ms)")
    rec = store.add_annotation(sid, body.model_dump())
    return {"ok": True, "annotation": rec}


@api.get("/sessions/{sid}/annotation")
def get_annotations(sid: str, request: Request):
    _require_admin(request)
    """Expert process labels, plus the replay boundaries they were drawn against."""
    _session_or_404(sid)
    return {"session_id": sid, "labels": list(PROCESS_LABELS),
            "annotations": store.labels(sid, "process_annotation")}


@api.post("/sessions/{sid}/badges")
def report_badges(sid: str, body: EarnedBadges):
    """Record which badges this session lit, under which rule set."""
    _session_or_404(sid)
    rec = body.model_dump()
    rec["at"] = now_iso()
    store.update(sid, badges=rec)
    return {"ok": True, "badges": rec}


# -- gallery: other people's approaches, never a ranking of children ----------
@api.get("/gallery/task/{task_id}")
def gallery_for_task(task_id: str, exclude: str = "", k: int = 3):
    """Approaches to this task that differ most from the viewer's.

    Only sessions whose frozen condition carries `share_consent` are eligible —
    showing one child's drawing to another is publication, and consent for it
    is a separate box on the form.
    """
    viewer = None
    if exclude:
        try:
            viewer = store.load(exclude)
        except KeyError:
            viewer = None
    return gallery_mod.diverse_examples(task_id, exclude_session=exclude,
                                        k=max(1, min(6, k)), viewer_meta=viewer)


@api.get("/gallery/featured")
def gallery_featured(task_id: str = "", k: int = 8):
    """Work that was picked **and** that the child then agreed to show."""
    return gallery_mod.featured_examples(task_id, k=max(1, min(24, k)))


@api.post("/gallery/curate")
def gallery_curate(body: Curate, request: Request):
    _require_admin(request)
    """今天挂哪几张。一天跑一次（cron → `tools/curate.py`）。

    这里只是**提议**，和老师 pin 走同一条路：每一张都要等本人下次打开 app
    时自己答应，才会挂出来。挑的规则在 `gallery.curate` —— 轮换 + 差异，
    不是排名，理由见那儿的注释。重复跑是安全的：已经提过的不会再提一次。
    """
    picks = gallery_mod.curate(k=body.k, since=body.since,
                               cooldown_days=body.cooldown_days)
    out = []
    for p in picks:
        rec = store.propose_featured(p["session_id"], by=gallery_mod.CURATOR_ID, note=p["why"])
        if rec.get("state") == "pending":
            out.append({"session_id": p["session_id"], "task_id": p["task_id"], "why": p["why"]})
    log.info("curated %d session(s) for the wall", len(out))
    return {"proposed": out, "count": len(out), "by": gallery_mod.CURATOR_ID}


@api.get("/achievements")
def achievements():
    """How rare each badge is across everyone — collection, not comparison."""
    return gallery_mod.achievement_stats()


@api.get("/sessions/{sid}/personalization")
def get_personalization(sid: str):
    """Exactly what the system knew and decided before this child drew."""
    _session_or_404(sid)
    rec = store.personalization(sid)
    if rec is None:
        raise HTTPException(404, "no personalization recorded for this session")
    return rec


# -- participants: behavioural history → user representation ------------------
@api.get("/participants/{pid}/history")
def participant_history(pid: str, request: Request, anon_id: str = "", account_id: str = "", before: str = ""):
    _check_owner(request, account_id)
    """A participant's finished tasks, compacted — the input to a representation."""
    sc = _scope(account_id)
    metas = history_mod.sessions_for(pid, anon_id, account_id=sc["account_id"],
                                     windows=sc["device_windows"], before=before)
    return {"participant_id": pid, "anon_id": anon_id, "n_tasks": len(metas),
            "tasks": [history_mod.task_record(m) for m in metas]}


@api.get("/participants/{pid}/protocol")
def participant_protocol(pid: str, request: Request, anon_id: str = ""):
    _require_admin(request)
    """Planned order vs what actually happened.

    Task order is a confound, so it is checked rather than assumed: a run that
    drifted from its plan (a skipped task, a repeat, a different form) shows up
    here instead of quietly entering the analysis.
    """
    roster = study_mod.roster_entry(pid)
    planned = list(roster.get("planned_order") or [])
    done = history_mod.sessions_for(pid, anon_id)
    actual = [m.get("quest_id") for m in done]
    return {
        "participant_id": pid, "protocol_id": roster.get("protocol_id", ""),
        "planned_order": planned, "actual_order": actual,
        "completed": len(actual), "planned": len(planned),
        "followed_plan": actual == planned[:len(actual)],
        "missing": [t for t in planned if t not in actual],
        "unplanned": [t for t in actual if planned and t not in planned],
        "repeats": sorted({t for t in actual if actual.count(t) > 1}),
    }


@api.get("/participants/{pid}/growth")
def participant_growth(pid: str, request: Request, anon_id: str = "", account_id: str = ""):
    _check_owner(request, account_id)
    """The nine attributes, in two layers: practice (real today) and evaluation
    (asleep until a backend can actually judge that dimension)."""
    sc = _scope(account_id)
    return history_mod.growth(pid, anon_id, account_id=sc["account_id"], windows=sc["device_windows"])


@api.get("/participants/{pid}/representation")
def participant_representation(pid: str, request: Request, anon_id: str = "", account_id: str = "", before: str = ""):
    _check_owner(request, account_id)
    """Rebuilt from the logs on every call — never a stored summary.

    `before` (ISO timestamp) reproduces the input a past decision had.
    """
    sc = _scope(account_id)
    return history_mod.build(pid, anon_id, account_id=sc["account_id"],
                             windows=sc["device_windows"], before=before)


@api.post("/sessions/{sid}/qc")
def rerun_qc(sid: str, request: Request):
    _require_admin(request)
    _session_or_404(sid)
    return _run_qc(sid)


# 同一套接口，两个前缀。`/api/v1` 是正式的名字（网页版和 app 都调它）；
# `/api` 是当前版本的别名。将来真要改契约就再挂一个 `/api/v2`，v1 原样留着。
app.include_router(api, prefix="/api/v1")
app.include_router(api, prefix="/api", generate_unique_id_function=lambda r: "alias_" + r.name)
