"""FastAPI application: serves the drawing UI and the session / research API."""
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import events as ev
from . import gallery as gallery_mod
from . import history as history_mod
from . import study as study_mod
from .accounts import AccountError, AccountStore
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
    AssistIn,Abandon, Annotation, ClaimDevice, CreateSession, Curate, DrawEvent, EarnedBadges,
                      FeaturedAnswer, FeedbackIn, Finalize, HARDEST_PARTS_SHOWN, IssueTickets, Login, LogBatch,
                      PROCESS_LABELS, ProfileUpdate, Questionnaire, Rating, Register, Snapshot, StudyAssign,
                      Stroke, Submit, TokenOnly)
from .scoring import DIMENSIONS, SCALE_MAX, get_scorer
from .storage import SCHEMA_VERSION, SessionStore, decode_data_url, now_iso, sid_of

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
_SHELL_FILES = ("index.html", "app.js", "log.js", "style.css", "sw.js")


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
    if path == "/" or path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


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


@app.get("/api/config")
def config():
    scorer, fb = get_scorer(), get_feedback_engine()
    st = study_mod.load_study()
    return {
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


@app.get("/api/families")
def get_families():
    """Mission families — what the child picks from; a form is assigned below."""
    return task_families()


@app.get("/api/quests")
def quests():
    return QUESTS


# -- study mode ------------------------------------------------------------
@app.get("/api/study")
def study_config():
    return study_mod.load_study()


@app.post("/api/study/assign")
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


@app.post("/api/accounts/register", status_code=201)
def account_register(body: Register):
    try:
        return accounts.register(body.name, body.pin, anon_id=body.anon_id, buddy_name=body.buddy_name)
    except AccountError as e:
        raise _account_error(e)


@app.post("/api/accounts/login")
def account_login(body: Login):
    try:
        return accounts.login(body.name, body.pin, anon_id=body.anon_id)
    except AccountError as e:
        raise _account_error(e)


@app.get("/api/accounts/me")
def account_me(token: str = "", anon_id: str = ""):
    """当前登录的是谁，外加「这台设备上还有几张没归属的画」——
    那个数字是「收进我的」按钮存在的全部理由，所以在这儿一起给。"""
    try:
        acc = accounts.require(token)
    except AccountError as e:
        raise _account_error(e)
    pub = accounts.public(acc)
    claimed = anon_id in accounts.device_windows(acc)
    return {"account": pub, "unclaimed_here": 0 if claimed else len(store.unowned(anon_id)),
            "claimed_here": claimed}


@app.post("/api/accounts/claim")
def account_claim(body: ClaimDevice):
    """把这台设备上以前画的收进自己名下。**不改任何 session**：
    记的是「这个账号认领过这台设备，截止到此刻」，旧数据一个字节不动。"""
    try:
        acc = accounts.require(body.token)
        pub = accounts.claim_device(acc["account_id"], body.anon_id)
    except AccountError as e:
        raise _account_error(e)
    return {"ok": True, "account": pub, "claimed": len(store.unowned(body.anon_id))}


@app.post("/api/accounts/profile")
def account_profile(body: ProfileUpdate):
    """伙伴的名字跟着账号走，换台设备它还叫原来那个名字。"""
    try:
        acc = accounts.require(body.token)
        return {"ok": True, "account": accounts.set_buddy_name(acc["account_id"], body.buddy_name)}
    except AccountError as e:
        raise _account_error(e)


@app.post("/api/accounts/logout")
def account_logout(body: TokenOnly):
    """只退这一台设备。别处仍然登录着——共用 iPad 上退出的那个孩子，
    不该把自己手机上的登录也一起弄掉。"""
    accounts.logout(body.token)
    return {"ok": True}


# -- sessions --------------------------------------------------------------
@app.get("/api/sessions")
def list_sessions(participant_id: str = "", anon_id: str = "", account_id: str = ""):
    """不带参数 = 研究员看全部；带上身份 = 这个孩子自己的那些（app 永远带）。"""
    return store.list(participant_id=participant_id, anon_id=anon_id, **_scope(account_id))


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    try:
        return store.load_full(sid)
    except KeyError:
        raise HTTPException(404, "session not found")


@app.get("/api/sessions/{sid}/strokes")
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


@app.post("/api/tickets", status_code=201)
def issue_tickets(body: IssueTickets):
    """预发几张票，留着离线用。

    一张票 = 服务端生成的 `session_id` + **此刻冻结好的 condition**，目录当场占住。
    孩子离线开始创作就是花掉一张，不发任何请求；重新联网时队列把创建和笔画一起补上。

    为什么不让客户端自己发 id：那会一次性毁掉三样东西——id 的可信性（它是后面
    每张表的外键）、条件冻结（孩子究竟跑在哪条实验臂上），以及重放时分不清
    「这个 session 还没建」和「这个 session 根本不存在」。票据把服务端的决定
    **提前**而不是拿掉。
    """
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


@app.post("/api/sessions", status_code=201)
def create_session(body: CreateSession):
    quest = QUESTS_BY_ID.get(body.task())
    if quest is None:
        raise HTTPException(400, "unknown quest")
    st = body.study.model_dump()
    condition = study_mod.resolve_condition(body.condition, st.get("group", ""))
    if quest.get("time_limit_sec") and not condition.get("time_limit_sec"):
        condition["time_limit_sec"] = quest["time_limit_sec"]
    try:
        meta = store.create(
            quest, body.intent.model_dump(),
            participant=body.participant_dict(), condition=condition,
            device=body.device.model_dump(), study=st, canvas=body.canvas.model_dump(),
            sid=body.session_id or None,
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


@app.post("/api/sessions/{sid}/log")
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


@app.post("/api/sessions/{sid}/assist")
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
    quest = QUESTS_BY_ID[meta["quest_id"]]
    try:
        out = get_assist_engine().assist(png, quest, meta.get("intent") or {}, nth=max(1, body.nth))
    except Exception as e:                      # 陪伴挂了绝不能挡住画画
        log.exception("assist failed")
        return {"text": "我在这儿呢，接着画。", "backend": "error", "error": str(e)}
    return {"text": out["text"], "backend": out.get("backend", "")}


@app.post("/api/sessions/{sid}/snapshot")
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
    quest, intent = QUESTS_BY_ID[meta["quest_id"]], meta["intent"]
    store.save_phase_image(sid, phase, png)
    try:
        scores = get_scorer().score(png, quest, intent)
    except Exception as e:  # scoring must never lose the artwork
        log.exception("scoring failed")
        scores = {"backend": "error", "scale": [1, SCALE_MAX], "dims": {}, "summary": f"评分失败：{e}"}
    # N/A is not a low score: a dimension this task cannot elicit carries no number
    scores = apply_contract(scores, quest.get("rubric"))
    return {"file": f"{phase}.png", "elapsed_ms": elapsed_ms, "at": now_iso(), "scores": scores}


@app.post("/api/sessions/{sid}/submit")
def submit(sid: str, body: Submit):
    meta = _session_or_404(sid)
    try:
        png = decode_data_url(body.image)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _ingest(sid, body.events, body.strokes)
    quest, intent = QUESTS_BY_ID[meta["quest_id"]], meta["intent"]
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


@app.post("/api/sessions/{sid}/finalize")
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


@app.post("/api/sessions/{sid}/abandon")
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


@app.post("/api/sessions/{sid}/questionnaire")
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


@app.post("/api/sessions/{sid}/feedback")
def add_feedback(sid: str, body: FeedbackIn):
    """Record a teacher's or the child's own feedback next to the AI's.

    `target_region` is in canvas pixel space, the same coordinates strokes use,
    so `/revision` can answer whether the child then worked where it pointed.
    """
    _session_or_404(sid)
    rec = store.add_feedback(sid, body.model_dump())   # the record *is* the event
    return {"ok": True, "feedback": rec}


@app.post("/api/sessions/{sid}/rating")
def add_rating(sid: str, body: Rating):
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


@app.get("/api/participants/{pid}/featured")
def featured_pending(pid: str, anon_id: str = "", account_id: str = ""):
    """这个孩子有哪几张被老师挑中、还等着他自己答复。"""
    sc = _scope(account_id)
    out = []
    for meta in history_mod.sessions_for(pid, anon_id, account_id=sc["account_id"],
                                         windows=sc["device_windows"]):
        rec = meta.get("featured") or {}
        if rec.get("state") != "pending":
            continue
        sid = sid_of(meta)
        quest = QUESTS_BY_ID.get(meta.get("quest_id")) or {}
        out.append({"session_id": sid, "task_id": meta.get("quest_id"),
                    "title": quest.get("title") or meta.get("quest_id"),
                    "image": f"/files/{sid}/final.png",
                    "by": rec.get("by", ""), "note": rec.get("note", ""),
                    "proposed_at": rec.get("proposed_at")})
    return {"participant_id": pid, "pending": out}


@app.post("/api/sessions/{sid}/featured")
def answer_featured(sid: str, body: FeaturedAnswer):
    """孩子自己的答复。答应了才会挂到大家那面墙上；随时可以反悔。"""
    _session_or_404(sid)
    return {"ok": True, "featured": store.answer_featured(sid, body.accept)}


@app.get("/api/sessions/{sid}/revision")
def get_revision(sid: str):
    """Feedback → what the child did next, in time and (when targeted) in space.

    Derived from the logs on request, never stored: the relation improves when
    the analysis does.
    """
    _session_or_404(sid)
    return attribute_revision(store.dir(sid))


@app.post("/api/sessions/{sid}/annotation")
def add_annotation(sid: str, body: Annotation):
    """An expert labelling a stretch of the replay (planning / revision / …)."""
    meta = _session_or_404(sid)
    duration = (meta.get("times") or {}).get("duration_ms")
    if duration and body.t_start_ms > duration:
        raise HTTPException(422, f"span starts after the session ended ({duration} ms)")
    rec = store.add_annotation(sid, body.model_dump())
    return {"ok": True, "annotation": rec}


@app.get("/api/sessions/{sid}/annotation")
def get_annotations(sid: str):
    """Expert process labels, plus the replay boundaries they were drawn against."""
    _session_or_404(sid)
    return {"session_id": sid, "labels": list(PROCESS_LABELS),
            "annotations": store.labels(sid, "process_annotation")}


@app.post("/api/sessions/{sid}/badges")
def report_badges(sid: str, body: EarnedBadges):
    """Record which badges this session lit, under which rule set."""
    _session_or_404(sid)
    rec = body.model_dump()
    rec["at"] = now_iso()
    store.update(sid, badges=rec)
    return {"ok": True, "badges": rec}


# -- gallery: other people's approaches, never a ranking of children ----------
@app.get("/api/gallery/task/{task_id}")
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


@app.get("/api/gallery/featured")
def gallery_featured(task_id: str = "", k: int = 8):
    """Work that was picked **and** that the child then agreed to show."""
    return gallery_mod.featured_examples(task_id, k=max(1, min(24, k)))


@app.post("/api/gallery/curate")
def gallery_curate(body: Curate):
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


@app.get("/api/achievements")
def achievements():
    """How rare each badge is across everyone — collection, not comparison."""
    return gallery_mod.achievement_stats()


@app.get("/api/sessions/{sid}/personalization")
def get_personalization(sid: str):
    """Exactly what the system knew and decided before this child drew."""
    _session_or_404(sid)
    rec = store.personalization(sid)
    if rec is None:
        raise HTTPException(404, "no personalization recorded for this session")
    return rec


# -- participants: behavioural history → user representation ------------------
@app.get("/api/participants/{pid}/history")
def participant_history(pid: str, anon_id: str = "", account_id: str = "", before: str = ""):
    """A participant's finished tasks, compacted — the input to a representation."""
    sc = _scope(account_id)
    metas = history_mod.sessions_for(pid, anon_id, account_id=sc["account_id"],
                                     windows=sc["device_windows"], before=before)
    return {"participant_id": pid, "anon_id": anon_id, "n_tasks": len(metas),
            "tasks": [history_mod.task_record(m) for m in metas]}


@app.get("/api/participants/{pid}/protocol")
def participant_protocol(pid: str, anon_id: str = ""):
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


@app.get("/api/participants/{pid}/growth")
def participant_growth(pid: str, anon_id: str = "", account_id: str = ""):
    """The nine attributes, in two layers: practice (real today) and evaluation
    (asleep until a backend can actually judge that dimension)."""
    sc = _scope(account_id)
    return history_mod.growth(pid, anon_id, account_id=sc["account_id"], windows=sc["device_windows"])


@app.get("/api/participants/{pid}/representation")
def participant_representation(pid: str, anon_id: str = "", account_id: str = "", before: str = ""):
    """Rebuilt from the logs on every call — never a stored summary.

    `before` (ISO timestamp) reproduces the input a past decision had.
    """
    sc = _scope(account_id)
    return history_mod.build(pid, anon_id, account_id=sc["account_id"],
                             windows=sc["device_windows"], before=before)


@app.post("/api/sessions/{sid}/qc")
def rerun_qc(sid: str):
    _session_or_404(sid)
    return _run_qc(sid)
