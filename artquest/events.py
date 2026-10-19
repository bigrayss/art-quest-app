# -*- coding: utf-8 -*-
"""The unified event vocabulary — one timeline, one clock.

Every module writes into the same stream with the same clock, so nothing has to
be reconciled afterwards:

* `t_ms` is **the** timestamp: milliseconds since the session started drawing,
  read off the client's `Date.now()`. The wall clock at `t_ms = 0` is the
  client's own reading, logged once as the `SYNC_MARK` with `n = 0` (see
  `client_clock_anchor`). It is *not* `times.started_at`: that one is the
  server's clock at the moment it handled the create request — a round trip
  earlier, on another machine, and for an offline ticket whenever the create
  was finally replayed. So no other event carries a wall clock, and no two
  modules can disagree about what "now" was.
* Server-side records (feedback shown, session end) land in the same stream with
  the same `t_ms`, taken from the client's clock at the request that caused them.

Some names changed when the vocabulary was unified. Renaming without an alias
would orphan the sessions already collected, so `canonical()` folds the old name
onto the new one and every reader goes through it. Old logs keep their bytes;
readers stop caring.
"""
from typing import Any, Dict, Iterable, Optional, Set

# -- session / task ----------------------------------------------------------
SESSION_START = "SESSION_START"
TASK_SHOW = "TASK_SHOW"
CANVAS_GEOMETRY = "CANVAS_GEOMETRY"
TASK_SUBMIT = "TASK_SUBMIT"
SESSION_ABANDONED = "SESSION_ABANDONED"   # the child backed out before submitting
SESSION_END = "SESSION_END"

# -- drawing -----------------------------------------------------------------
STROKE_START = "STROKE_START"
STROKE_CANCELLED = "STROKE_CANCELLED"
STROKE_END = "STROKE_END"
ERASE = "ERASE"
UNDO = "UNDO"
REDO = "REDO"
CLEAR = "CLEAR"

# -- tools -------------------------------------------------------------------
BRUSH_CHANGE = "BRUSH_CHANGE"
COLOR_CHANGE = "COLOR_CHANGE"
SIZE_CHANGE = "SIZE_CHANGE"
# 浓淡原本是工具写死的属性，孩子动不了；放开成一个滑杆之后它也成了一个选择，
# 和换颜色、换粗细同级。不是改名，是新词——旧日志里本来就没有它。
OPACITY_CHANGE = "OPACITY_CHANGE"

# -- view --------------------------------------------------------------------
ZOOM = "ZOOM"
PAN = "PAN"

# -- reference ---------------------------------------------------------------
REFERENCE_SHOW = "REFERENCE_SHOW"        # presented by the task
REFERENCE_OPEN = "REFERENCE_OPEN"        # the child opened it
REFERENCE_CLOSE = "REFERENCE_CLOSE"
REFERENCE_ZOOM = "REFERENCE_ZOOM"
REFERENCE_PAN = "REFERENCE_PAN"
REFERENCE_COLOR_PICK = "REFERENCE_COLOR_PICK"   # 从参考图里吸了一个颜色
REFERENCE_FOCUS = "REFERENCE_FOCUS"      # attention moved to the reference
CANVAS_FOCUS = "CANVAS_FOCUS"            # …and back to the canvas
# 首访任务库（2026-10-12）：孩子主动点开一条固定提示。payload：hint_id（H1/H2）、task_id、第几次点。
# 看过提示 ≠ 没独立思考，也不能当作「未受帮助」数据——所以记的是事实，不记判断。
HINT_SHOW = "HINT_SHOW"

# -- attention ---------------------------------------------------------------
PAUSE_START = "PAUSE_START"
PAUSE_END = "PAUSE_END"
TIME_LIMIT_REACHED = "TIME_LIMIT_REACHED"

# -- 创作进行中的陪伴 ---------------------------------------------------------
# 孩子主动点开那扇模糊的窗，听彩点说一句话。**他点的那一刻**才是信号：
# 点了几次、第一次点在创作进行到多久、点的时候画布是什么样——这些和 stroke
# 流对得上，是「AI 什么时候被需要」的直接证据，比一段聊天记录好编码得多。
# 连点命中冷却时也照记（带 cached=true），否则「想看」的次数会被吃掉。
ASSIST_OPEN = "ASSIST_OPEN"
# 那句话真的显示出来了（客户端记）：click_id、call_id（calls.jsonl 里生成它的那次执行）、
# cached（冷却期内再点，看到的是同一句 → source_call_id 指向原来那次）。
# 点了 ≠ 生成了 ≠ 显示了，三件事三条记录。
ASSIST_SHOW = "ASSIST_SHOW"
# 精灵换了形象 / 模式：role（normal/happy/thinking/explore/reading/encourage）、
# mode（companion / companion_quiet / waiting / one_shot / static）、reason（view /
# assist_request / assist_reply / request / save_ok）、view、asset_v（素材版本）。
# 安静模式的进出不记：那是「落笔 / 最后一笔后 2 秒」的确定规则，能从 stroke 流算回来。
MASCOT_STATE = "MASCOT_STATE"

# -- feedback / revision -----------------------------------------------------
FEEDBACK_SHOW = "FEEDBACK_SHOW"
FEEDBACK_DISMISS = "FEEDBACK_DISMISS"
# 模型挂了（key 失效、超时、形状不对），这一步退回了启发式评分 / 模板反馈 / 模板陪伴（2026-10-18）：
# purpose（score|review|final|assist）、from（本来该答的 backend）、to（实际答的）、error。孩子看到的是 to 给的东西。
MODEL_FALLBACK = "MODEL_FALLBACK"
REVISION_START = "REVISION_START"
REVISION_SKIPPED = "REVISION_SKIPPED"
HISTORY_SHOWN = "HISTORY_SHOWN"
RATING_ADDED = "RATING_ADDED"
# 被老师选为优秀作品 → 先问孩子，答了才算数
FEATURED_PROPOSED = "FEATURED_PROPOSED"
FEATURED_ACCEPTED = "FEATURED_ACCEPTED"
FEATURED_DECLINED = "FEATURED_DECLINED"

# -- outcome -----------------------------------------------------------------
QUESTIONNAIRE_SUBMITTED = "QUESTIONNAIRE_SUBMITTED"
DOWNLOAD = "DOWNLOAD"
# 纸面 session（condition.medium = paper，2026-10-19）收到一张作品照片或扫描件。payload：
# artifact_id、kind（final 终稿 / stage 阶段照）、sha256、uploaded_by、label、superseded（被它取代的旧终稿）。
# t_ms 是上传那一刻的会话时钟；拍摄时间记在 session.json 的 artifacts 里，不在这里。
ARTIFACT_UPLOADED = "ARTIFACT_UPLOADED"

# -- clocks ------------------------------------------------------------------
# 这条时间线和外面的钟对上的地方（2026-10-19）。payload：n、source、visible，n=0 另带 wall_ms。
# - n=0, source=clock, visible=false：时钟锚点。每个 session 一条，客户端在零点附近记，
#   t_ms 和 wall_ms 出自同一次 Date.now()，锚点 = wall_ms − t_ms（见 client_clock_anchor）。
# - n≥1, visible=true：看得见的同步标记，只在条件 sync_marks 打开时出现——整屏白闪一下、
#   显示编号 n，让眼动眼镜的场景相机、俯拍相机拍到同一帧。source = start（进画布自己闪一次）
#   / researcher（研究员按钮）/ submit（交卷那一下；纸面 session 是按「结束」那一下）。t_ms 记在白屏插进页面那一刻，
#   真正上屏还要等下一帧（≤ 1 帧）加屏幕延迟，试点时用视频实测。
#   不带 wall_ms：它就是锚点 + t_ms，能算出来的不存。
SYNC_MARK = "SYNC_MARK"

# Old name -> unified name. Sessions recorded before the vocabulary settled keep
# their bytes; every reader folds them onto the current name.
ALIASES: Dict[str, str] = {
    "STROKE": STROKE_END,          # one record was written, at the end of the stroke
    "IDLE_START": PAUSE_START,
    "IDLE_END": PAUSE_END,
    "FEEDBACK_SHOWN": FEEDBACK_SHOW,
}

VOCABULARY: Set[str] = {
    SESSION_START, TASK_SHOW, CANVAS_GEOMETRY, TASK_SUBMIT, SESSION_ABANDONED, SESSION_END,
    STROKE_START, STROKE_CANCELLED, STROKE_END, ERASE, UNDO, REDO, CLEAR,
    BRUSH_CHANGE, COLOR_CHANGE, SIZE_CHANGE, OPACITY_CHANGE, ZOOM, PAN,
    REFERENCE_SHOW, REFERENCE_OPEN, REFERENCE_CLOSE, REFERENCE_ZOOM,
    REFERENCE_PAN, REFERENCE_FOCUS, CANVAS_FOCUS, REFERENCE_COLOR_PICK, HINT_SHOW,
    PAUSE_START, PAUSE_END, TIME_LIMIT_REACHED,
    ASSIST_OPEN, ASSIST_SHOW, MASCOT_STATE,
    FEEDBACK_SHOW, FEEDBACK_DISMISS, REVISION_START, REVISION_SKIPPED, MODEL_FALLBACK,
    HISTORY_SHOWN, RATING_ADDED, QUESTIONNAIRE_SUBMITTED, DOWNLOAD, ARTIFACT_UPLOADED,
    FEATURED_PROPOSED, FEATURED_ACCEPTED, FEATURED_DECLINED,
    SYNC_MARK,
}

# The strokes that actually put ink on the canvas, under either vocabulary.
DRAW_TYPES = (STROKE_END, ERASE)


def canonical(type_: str) -> str:
    """The unified name for an event type, old or new."""
    return ALIASES.get(type_, type_)


def is_known(type_: str) -> bool:
    return canonical(type_) in VOCABULARY


def unknown_types(types: Iterable[str]) -> Set[str]:
    """Event types not in the vocabulary — a module inventing its own name."""
    return {t for t in types if t and not is_known(t)}


def client_clock_anchor(events: Iterable[Dict[str, Any]]) -> Optional[int]:
    """The client's wall clock at `t_ms = 0`, in ms since the epoch.

    Read off the `SYNC_MARK` with `n = 0`: `wall_ms − t_ms`, both from one
    `Date.now()`. `None` when the session has no such mark — a client from
    before it existed — which is "not recorded", never 1970.
    """
    for e in events:
        p = e.get("payload") or {}
        if canonical(e.get("type", "")) == SYNC_MARK and p.get("n") == 0 and p.get("wall_ms") is not None:
            return int(p["wall_ms"]) - int(e.get("t_ms") or 0)
    return None


def visible_sync_marks(events: Iterable[Dict[str, Any]]) -> int:
    """How many on-screen sync marks the session shows (n ≥ 1)."""
    return sum(1 for e in events if canonical(e.get("type", "")) == SYNC_MARK
               and (e.get("payload") or {}).get("visible"))


# ---------------------------------------------------------------------------
# Strokes carry a vocabulary too, and it converged the same way event names did.
# ---------------------------------------------------------------------------
# What a raw stroke is, and nothing else:
#
#     geometry + time + tool state
#
# Anything derivable stays out of the record — `t_end_ms` is `t0_ms` plus the
# last point's `dt`, and speed / curvature / length belong to analysis. Two
# fields that look derivable are kept on purpose: `zoom` is what the child could
# see while drawing this stroke, and `pressure_supported` / `tilt_supported` say
# *why* a null is null — no sensor, rather than a sensor that read nothing.
STROKE_FIELDS = ("stroke_id", "seq", "phase", "op", "tool", "color", "size", "opacity",
                 "pointer", "pressure_supported", "tilt_supported", "zoom", "t0_ms", "points")
_STROKE_ALIASES = {"t_start_ms": "t0_ms", "pointer_type": "pointer"}


def canonical_stroke(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Fold an older stroke record onto the current field names.

    Same contract as `canonical()` for event names: the file on disk is never
    rewritten, every reader goes through here.
    """
    out = dict(rec)
    for old, new in _STROKE_ALIASES.items():
        if old in out:
            out.setdefault(new, out[old])
            out.pop(old)
    if "op" not in out:
        out["op"] = "erase" if out.pop("erase", False) else "draw"
    out.pop("erase", None)
    out.pop("t_end_ms", None)          # exactly t0_ms + points[-1][2]
    return out


def stroke_end_ms(rec: Dict[str, Any]) -> float:
    """When the pen came up — from the record, or from its last sample."""
    if rec.get("t_end_ms") is not None:
        return float(rec["t_end_ms"])
    t0 = float(rec.get("t0_ms") if rec.get("t0_ms") is not None else rec.get("t_start_ms") or 0)
    pts = rec.get("points") or []
    return t0 + float(pts[-1][2] or 0) if pts else t0


def stroke_start_ms(rec: Dict[str, Any]) -> float:
    """When the pen went down, under either spelling."""
    v = rec.get("t0_ms")
    return float(v if v is not None else (rec.get("t_start_ms") or 0))
