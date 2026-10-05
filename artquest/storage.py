"""Session store — stroke/event logs are the primary data, images are aids.

Four data files, not fifteen:

    data/sessions/<session_id>/
        session.json       everything small and non-time-series: identity, the
                           frozen task definition, condition, device, canvas,
                           timing, personalisation, self-report, QC
        strokes.jsonl[.gz] the drawing itself, one line per stroke
        events.jsonl[.gz]  every non-drawing operation — and feedback, which is
                           an event on the same timeline, not a second file
        labels.jsonl       human ground truth: teacher ratings + expert spans
        final.png          the last submitted work
        checkpoints/before_feedback.png   only when a revision actually happened
        reference/         the stimulus this child saw (static/refs gets replaced)

Sessions recorded under the older split layout (metadata.json + condition.json +
self_report.json + personalization.json + quality.json + feedback/ratings/
annotations.jsonl) are read as they are — **old data is never rewritten**, the
readers below fold it onto the current shape, the same contract `events.canonical`
gives event names.

Client records carry a monotonic `seq` per stream; appends drop anything at or
below the stored high-water mark, so an offline client can safely re-send.
Finished streams are gzipped; reads and late appends are transparent.
"""
import base64
import hashlib
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from . import config          # read through the module: the data dir is env-driven
                             # and tests reload it, so binding the value at import
                             # time would freeze the production path
from . import events as ev
from .logstore import JsonlLog, read_json, write_json

SCHEMA_VERSION = 3

# Where a session is in its journey from the child's screen to a verified row.
# Separate from `status` (which says where the *child* is): a finished drawing
# whose last batch never uploaded is done for the child and not done for the data.
# `issued` 是一张**预发的票**：id 和条件已经由服务端定死，但孩子还没开始画。
# 它排在 recording 前面，所以「只进不退」那条规则原样成立（比的是序号）。
# 票据存在的理由见 DESIGN.md「离线创作」：设备离线时不能自己编一个 session_id，
# 更不能自己编一条实验臂——那两样都是后面每张表的地基。
LIFECYCLE = ("issued", "recording", "completed_local", "pending_upload", "uploaded", "server_verified")
_DATAURL_RE = re.compile(r"^data:image/(png|jpeg);base64,(.+)$", re.DOTALL)
# Logical streams a caller asks for -> the physical file they live in. Feedback
# is an event; a rating and an expert span are both human labels.
_STREAMS = ("events", "strokes", "feedback", "ratings", "annotations")
_STREAM_FILE = {"events": "events", "strokes": "strokes", "feedback": "events",
                "ratings": "labels", "annotations": "labels"}
_LABEL_TYPE = {"ratings": "rating", "annotations": "process_annotation"}


def now_iso() -> str:
    """UTC, to the millisecond.

    Seconds are not enough: two sessions started in the same second cannot be
    ordered, and the history window (`history.build(before=...)`, which has to
    reproduce exactly what a past decision could see) would silently drop the
    earlier one. Still sorts lexicographically against older second-resolution
    stamps, so existing sessions stay comparable.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def decode_data_url(data_url: str) -> bytes:
    m = _DATAURL_RE.match(data_url.strip())
    if not m:
        raise ValueError("expected a PNG/JPEG data URL")
    return base64.b64decode(m.group(2))


class SessionStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or config.SESSIONS_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths -------------------------------------------------------------
    def dir(self, sid: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", sid):
            raise KeyError(sid)
        return self.root / sid

    def _meta_path(self, sid: str) -> Path:
        """`session.json` since schema 3 — and, by coincidence, schema 1's name.

        A schema-2 session keeps writing to its own `metadata.json`: converging
        the layout must not rewrite data that has already been collected.
        """
        d = self.dir(sid)
        return d / "metadata.json" if (d / "metadata.json").exists() else d / "session.json"

    def log(self, sid: str, stream: str) -> JsonlLog:
        """The physical append-only log a logical stream writes to.

        A session recorded when feedback / ratings / annotations each had their
        own file keeps appending there, so its records stay in one place.
        """
        d = self.dir(sid)
        own = JsonlLog(d / f"{stream}.jsonl")
        if stream in ("feedback", "ratings", "annotations") and not own.exists():
            return JsonlLog(d / f"{_STREAM_FILE[stream]}.jsonl")
        return own

    # -- lifecycle ---------------------------------------------------------
    def create(self, quest: Dict[str, Any], intent: Dict[str, Any], *,
               participant: Optional[Dict[str, Any]] = None,
               condition: Optional[Dict[str, Any]] = None,
               device: Optional[Dict[str, Any]] = None,
               study: Optional[Dict[str, Any]] = None,
               canvas: Optional[Dict[str, Any]] = None,
               sid: Optional[str] = None, lang: str = "zh") -> Dict[str, Any]:
        """开一次创作。

        `sid` 给了就是**花掉一张预发的票**（见 `issue`）：目录和 id 早就占住了，
        条件也早就冻好了。两条规矩：

        - **条件以票上的为准**，不是这一刻再算一遍。票是联网时发的，孩子离线
          画的时候跑的就是票上那条臂；重放时再 resolve 一次可能得到另一个答案
          （study.json 中间被改过），那样记下来的就不是孩子实际经历的东西。
        - **已经用过的票原样返回**。离线队列会重发，重发不能把一个已经有笔画的
          session 抹回空的。
        """
        ticket = None
        if sid:
            prev = self.load(sid)                    # 没发过这张票就 KeyError，不认
            if prev.get("lifecycle") != "issued":
                return prev                          # 用过了：幂等，绝不覆盖
            ticket = prev
            d = self.root / sid
        else:
            sid = uuid.uuid4().hex[:12]
            d = self.root / sid
            d.mkdir(parents=True)
        if ticket and ticket.get("condition"):
            condition = ticket["condition"]
        p = dict(participant or {})
        meta = {
            "schema_version": SCHEMA_VERSION,
            # The directory is named by the id; one copy inside is documentation,
            # two was just the old `id` field that never got cleaned up.
            "session_id": sid,
            "created_at": now_iso(),
            # -- identity: an anonymous device id always, a researcher code when given
            "participant": {
                "anon_id": p.get("anon_id", ""),
                "participant_id": p.get("participant_id", ""),
                # 孩子注册过就带上账号 id——「这些画是同一个人画的」在换设备之后
                # 唯一还成立的那根线。空着就是没登录，那时只有设备认得他。
                "account_id": p.get("account_id", ""),
                "label": p.get("label", ""),
                "age": p.get("age"),
                # 孩子给创作伙伴起的名字；有没有起名本身就是投入程度的信号
                "buddy_name": p.get("buddy_name", ""),
            },
            # -- task: same row the child sees as a level
            "quest_id": quest["id"],
            "task": {
                "task_id": quest["id"],
                # a task is a measurement object: which family, which parallel
                # form, in which prompt style, at which version of the library
                "family": quest.get("family", ""),
                "mission_family": quest.get("family_slug", ""),
                "form_id": quest.get("form_id", ""),
                "prompt_style": quest.get("prompt_style", ""),
                "task_version": quest.get("version", ""),
                "category": quest.get("category"),
                "difficulty": quest.get("difficulty"),
                "time_limit_sec": quest.get("time_limit_sec"),
                "allowed_tools": quest.get("allowed_tools"),
                "stimulus_id": quest.get("stimulus_id", ""),
                "stimulus_kind": (quest.get("stimulus") or {}).get("kind", "none"),
                "stimulus_placeholder": bool(quest.get("stimulus_placeholder")),
                "reference_id": (quest.get("reference") or {}).get("id"),
                "focus_dims": quest.get("focus_dims", []),
                "applicable_dims": quest.get("applicable_dims", []),
                "rubric": quest.get("rubric"),
                "process_targets": quest.get("process_targets", []),
                "order_index": (study or {}).get("order_index"),
                "sequence_id": (study or {}).get("sequence_id", ""),
            },
            # -- condition: frozen at creation, never changed mid-session
            "condition": dict(condition or {}),
            "study": {"active": bool((study or {}).get("active")), "study_id": (study or {}).get("study_id", ""),
                      "group": (study or {}).get("group", "")},
            "app": {"version": __version__, "schema": SCHEMA_VERSION},
            # 孩子看的是哪种语言的界面和题目：评分、反馈、陪伴之后都按它
            "lang": lang or "zh",
            "device": dict(device or {}),
            "canvas": dict(canvas or {}),
            "times": {"created_at": now_iso(), "started_at": None, "ended_at": None, "duration_ms": None},
            "intent": intent,
            "status": "drawing",
            "snapshots": [],
            "before": None,
            "after": None,
            "feedback": None,
            "comparison": None,
            "revised": None,
            "questionnaire": None,
            "lifecycle": "recording",
            # 这个 id 是当场生成的，还是花掉一张预发的票——离线创作的 session
            # 全是后者，分析时要分得开
            "id_source": "ticket" if ticket else "server",
            "issued_at": (ticket or {}).get("issued_at"),
            "streams": {s: {"last_seq": 0, "count": 0} for s in _STREAMS},
            "counts": {"strokes": 0, "points": 0, "events": 0, "snapshots": 0},
            # everything that used to be its own small file lives here now
            "personalization": None,
            "self_report": None,
            "qc": None,
        }
        self._write(sid, meta)
        return meta

    def issue(self, *, condition: Optional[Dict[str, Any]] = None,
              participant: Optional[Dict[str, Any]] = None,
              study: Optional[Dict[str, Any]] = None,
              quest_id: str = "") -> Dict[str, Any]:
        """预发一张票：把 id 和条件在**联网的时候**定死。

        离线创作要的不是「让客户端自己发 id」——那会一次性毁掉三样东西：
        id 的可信性（它是后面每张表的外键）、条件冻结（孩子到底跑在哪条臂上）、
        以及重放时分不清「这个 session 还没建」和「这个 session 不存在」。
        票据把服务端的决定**提前**而不是拿掉，三个一起解决。

        目录在这时就占住，所以 id 不可能撞车；`create` 花掉它时不会再 mkdir。
        """
        sid = uuid.uuid4().hex[:12]
        (self.root / sid).mkdir(parents=True)
        p = dict(participant or {})
        meta = {
            "schema_version": SCHEMA_VERSION,
            "session_id": sid,
            "lifecycle": "issued",
            "issued_at": now_iso(),
            "id_source": "ticket",
            "condition": dict(condition or {}),
            "participant": {"anon_id": p.get("anon_id", ""), "participant_id": p.get("participant_id", ""),
                            "account_id": p.get("account_id", ""),
                            "label": p.get("label", ""),
                "age": p.get("age"), "buddy_name": p.get("buddy_name", "")},
            "study": {"active": bool((study or {}).get("active")), "study_id": (study or {}).get("study_id", ""),
                      "group": (study or {}).get("group", "")},
            "quest_id": quest_id,
            "app": {"version": __version__, "schema": SCHEMA_VERSION},
        }
        self._write(sid, meta)
        return meta

    # -- lifecycle ---------------------------------------------------------
    def set_lifecycle(self, sid: str, state: str) -> Dict[str, Any]:
        """Advance the upload lifecycle. Never moves backwards.

        A session that reached `uploaded` cannot be demoted by a late duplicate
        batch, and `server_verified` is only ever set by QC.
        """
        meta = self.load(sid)
        cur = meta.get("lifecycle", "recording")
        if state in LIFECYCLE and LIFECYCLE.index(state) > LIFECYCLE.index(cur):
            meta["lifecycle"] = state
            meta.setdefault("lifecycle_at", {})[state] = now_iso()
            self._write(sid, meta)
        return meta

    def log_checksum(self, sid: str) -> Dict[str, Any]:
        """Content hash of the two primary logs.

        Recorded when a session is verified, so later corruption or a partial
        re-upload is detectable rather than silently analysed.
        """
        out: Dict[str, Any] = {}
        for stream in ("events", "strokes"):
            path = self.dir(sid) / f"{stream}.jsonl"
            if path.exists():
                data = path.read_bytes()
                out[stream] = {"sha256": hashlib.sha256(data).hexdigest()[:32], "bytes": len(data)}
        return out

    def delete(self, sid: str) -> bool:
        """把一条 session 从盘上整个删掉。

        这个项目别处的规矩是**只标记不删**（QC 失败是标记，撤销的笔仍留在日志里）。
        真删只有两处：`tools/withdraw.py` 的撤回，和孩子在画廊里删自己的那一张。
        两处都是「同意被收回」，所以数据必须真的消失，而不是被标成可忽略。
        """
        d = self.root / sid
        if not d.is_dir():
            return False
        shutil.rmtree(d)
        return True

    def load(self, sid: str) -> Dict[str, Any]:
        meta = read_json(self._meta_path(sid))
        if meta is None:
            raise KeyError(sid)
        return meta

    def load_full(self, sid: str) -> Dict[str, Any]:
        """Metadata plus the log streams — what the API hands back."""
        meta = self.load(sid)
        if meta.get("schema_version", 1) >= 2:
            meta["events"] = self.log(sid, "events").read()
            meta["strokes_summary"] = self._strokes_summary(sid)
            meta["feedback_log"] = self.feedback_log(sid)
            meta["ratings"] = self.labels(sid, "rating")
            meta["annotations"] = self.labels(sid, "process_annotation")
            meta["condition_snapshot"] = self.condition_snapshot(sid)
            meta.setdefault("questionnaire", None)
            meta["questionnaire"] = meta["questionnaire"] or self.self_report(sid)
            meta["personalization"] = self.personalization(sid)
        meta.setdefault("events", [])
        return meta

    # -- personalisation ---------------------------------------------------
    # -- the condition the child actually saw -------------------------------
    def save_condition(self, sid: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Freeze the complete task definition into `session.json`'s `task`.

        `tasks.json` gets edited and the library grows; a task_id alone is not
        enough to recover what was on screen. Without this, a later reader
        resolves the id against a definition the child never saw. `frozen_at`
        marks the merged block as the real snapshot rather than the compact
        view `create()` writes.
        """
        meta = self.load(sid)
        meta["task"] = {**(meta.get("task") or {}), **snapshot, "frozen_at": now_iso()}
        self._write(sid, meta)
        return snapshot

    def condition_snapshot(self, sid: str) -> Optional[Dict[str, Any]]:
        return session_task(self.dir(sid)) or None

    def personalization(self, sid: str) -> Optional[Dict[str, Any]]:
        return session_part(self.dir(sid), "personalization")

    def save_personalization(self, sid: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Freeze what the system knew and decided *before* the child drew.

        Kept in its own file rather than recomputed later on purpose: the
        representation builder will improve, and a decision has to stay
        reproducible against the input it actually had.
        """
        record = dict(record, frozen_at=now_iso())
        meta = self.load(sid)
        meta["personalization"] = record
        meta["history_mode"] = record.get("requested_mode", "none")
        meta["personalization_backend"] = record.get("backend")
        self._write(sid, meta)
        return record

    def record_prediction_outcome(self, sid: str, answers: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Score the prediction written down at task start against the self-report.

        This is what turns three conditions into an evaluation: every arm wrote
        a number before the child drew, and here is the answer.
        """
        rec = self.personalization(sid)
        if not rec:
            return None
        pred = rec.get("prediction") or {}
        outcome, error = {}, {}
        for key in ("difficulty", "confidence"):
            actual, guess = answers.get(key), pred.get(key)
            if isinstance(actual, (int, float)) and isinstance(guess, (int, float)):
                outcome[key] = actual
                error[key] = round(guess - actual, 3)
        rec["outcome"] = outcome
        rec["error"] = error
        rec["scored_at"] = now_iso()
        meta = self.load(sid)
        if meta.get("personalization"):
            meta["personalization"] = rec
            self._write(sid, meta)
        else:                                    # older split layout: leave it there
            write_json(self.dir(sid) / "personalization.json", rec)
        return rec

    def _write(self, sid: str, meta: Dict[str, Any]) -> None:
        write_json(self._meta_path(sid), meta)

    def list(self, *, participant_id: str = "", anon_id: str = "", account_id: str = "",
             device_windows: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Every session, or just one child's.

        Unfiltered is the researcher's view. The app always asks for its own
        ids: once a server has more than one child on it — which is the
        whole point of putting it on a phone — an unfiltered list would put
        other children's drawings into this child's 画廊 and 小传, with no
        consent gate anywhere near it.

        `account_id` 是注册之后的那根线（见 `accounts.py`），
        `device_windows` 是 `{anon_id: 认领截止时刻}`：认领过的设备上、
        **认领之前**画的那些无主作品也算这个账号的。
        """
        keys = ("session_id", "created_at", "quest_id", "status", "revised", "badges", "featured")
        out = []
        for d in self.root.iterdir():
            if not d.is_dir():
                continue
            m = read_json(d / "session.json") or read_json(d / "metadata.json")
            if not m:
                continue
            # 没花掉的票不是作品：它没有画、没有时间、没有任务，
            # 出现在画廊里就是一个空壳
            if m.get("lifecycle") == "issued":
                continue
            if participant_id or anon_id or account_id:
                if not belongs_to(m, participant_id=participant_id, anon_id=anon_id,
                             account_id=account_id, windows=device_windows or {}):
                    continue
            row = {k: m.get(k) for k in keys}
            row["session_id"] = sid_of(m) or d.name
            p = m.get("participant")
            # 一行里只放一个「谁」：强的那个优先（代号 > 账号 > 设备），和别处一致
            row["participant"] = p if isinstance(p, str) else ((p or {}).get("participant_id")
                or (p or {}).get("account_id") or (p or {}).get("anon_id", ""))
            row["task_id"] = m.get("quest_id")
            row["qc_ok"] = (m.get("qc") or {}).get("ok")
            out.append(row)
        return sorted(out, key=lambda r: r.get("created_at") or "", reverse=True)

    def unowned(self, anon_id: str) -> List[str]:
        """这台设备上还没有归属的作品（anon_id 对得上、没有 account_id）。

        「把这台设备上以前画的收进我的」要先知道有几张——而这件事只有孩子
        自己点得下去，所以这里只数，不改任何东西。
        """
        if not anon_id:
            return []
        out = []
        for d in self.root.iterdir():
            if not d.is_dir():
                continue
            m = read_json(d / "session.json") or read_json(d / "metadata.json")
            if not m or m.get("lifecycle") == "issued":
                continue
            p = m.get("participant")
            p = p if isinstance(p, dict) else {}
            if p.get("anon_id") == anon_id and not p.get("account_id"):
                out.append(sid_of(m) or d.name)
        return out

    # -- log streams -------------------------------------------------------
    def append_client(self, sid: str, stream: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Idempotent ingest of a client batch. Returns the new stream state."""
        if stream not in _STREAMS:
            raise ValueError(f"unknown stream: {stream}")
        meta = self.load(sid)
        state = meta.setdefault("streams", {}).setdefault(stream, {"last_seq": 0, "count": 0})
        prev = int(state.get("last_seq", 0))
        # One clock: `t_ms` / `t0_ms` since the session started drawing, and the
        # wall clock recovered from `times.started_at`. A per-record timestamp
        # would be a second clock for the same fact, so records carry only
        # provenance. Strokes are folded onto the current field names on the way
        # in, so the file on disk is already canonical.
        norm = ev.canonical_stroke if stream == "strokes" else (lambda r: r)
        stamped = [dict(norm(r), src=r.get("src", "client")) for r in records]
        fresh = [r for r in stamped if int(r.get("seq") or 0) > prev]
        written, skipped, last = self.log(sid, stream).append_after(stamped, prev)
        state["last_seq"], state["count"] = last, int(state.get("count", 0)) + written
        counts = meta.setdefault("counts", {})
        if stream == "strokes":
            counts["strokes"] = state["count"]
            counts["points"] = int(counts.get("points", 0)) + sum(len(r.get("points") or []) for r in fresh)
        elif stream == "events":
            counts["events"] = state["count"]
        self._write(sid, meta)
        return {"stream": stream, "written": written, "skipped": skipped, "last_seq": last, "count": state["count"]}

    def add_server_event(self, sid: str, type_: str, t_ms: int = 0, payload: Optional[Dict[str, Any]] = None) -> None:
        """Log something the server did (feedback shown, revision skipped, …)."""
        self.log(sid, "events").append([
            {"seq": None, "src": "server", "t_ms": t_ms, "type": type_, "payload": payload}])
        meta = self.load(sid)
        meta.setdefault("counts", {})["events"] = self.log(sid, "events").count()
        self._write(sid, meta)

    def add_feedback(self, sid: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Record a feedback as what it is: an event on the process timeline.

        It used to be a second file plus a thin `FEEDBACK_SHOW` event pointing
        at it — the same fact written twice. One record now carries the whole
        thing, and `stroke / undo / feedback / pause / stroke` reads in order.
        """
        meta = self.load(sid)
        state = meta.setdefault("streams", {}).setdefault("feedback", {"last_seq": 0, "count": 0})
        payload = {
            "feedback_id": f"fb_{uuid.uuid4().hex[:8]}",
            "phase": record.get("phase", "before"),
            "source": record.get("source", "ai"),      # ai | teacher | self
            "feedback_type": record.get("feedback_type", "text"),
            "backend": record.get("backend", ""),
            "text": record.get("text", ""),
            "target_region": record.get("target_region"),
            "shown_at": record.get("shown_at") or now_iso(),
            # provenance, so a later model-generated intervention is comparable
            **{k: record[k] for k in ("trigger", "model", "prompt_version") if record.get(k)},
        }
        t_ms = record.get("t_ms", 0)
        # the event stream keeps one shape: type + payload, like every other event
        self.log(sid, "feedback").append(
            [{"seq": None, "src": "server", "t_ms": t_ms, "type": ev.FEEDBACK_SHOW, "payload": payload}])
        state["count"] = int(state.get("count", 0)) + 1
        meta.setdefault("counts", {})["events"] = self.log(sid, "events").count()
        self._write(sid, meta)
        return {**payload, "t_ms": t_ms}

    def feedback_log(self, sid: str) -> List[Dict[str, Any]]:
        """Every feedback shown — its own file in older sessions, an event since 3."""
        return session_feedback(self.dir(sid))

    def add_rating(self, sid: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Append a human rating. Append-only and rater-tagged on purpose:
        two teachers rating the same artwork is the normal case, and
        inter-rater agreement is something a dataset has to be able to report.
        """
        meta = self.load(sid)
        state = meta.setdefault("streams", {}).setdefault("ratings", {"last_seq": 0, "count": 0})
        rec = dict(record)
        rec.update({"type": "rating", "rating_id": f"rt_{uuid.uuid4().hex[:8]}",
                    "seq": None, "src": "server", "ts": now_iso()})
        self.log(sid, "ratings").append([rec])
        state["count"] = int(state.get("count", 0)) + 1
        meta.setdefault("counts", {})["ratings"] = state["count"]
        self._write(sid, meta)
        return rec

    def add_annotation(self, sid: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Append one expert span. Append-only and rater-tagged, like ratings."""
        meta = self.load(sid)
        state = meta.setdefault("streams", {}).setdefault("annotations", {"last_seq": 0, "count": 0})
        rec = dict(record)
        rec.update({"type": "process_annotation", "annotation_id": f"an_{uuid.uuid4().hex[:8]}",
                    "seq": None, "src": "server", "ts": now_iso()})
        self.log(sid, "annotations").append([rec])
        state["count"] = int(state.get("count", 0)) + 1
        meta.setdefault("counts", {})["annotations"] = state["count"]
        self._write(sid, meta)
        return rec

    def labels(self, sid: str, kind: str = "") -> List[Dict[str, Any]]:
        """Everything a human wrote down about this session (ratings + spans)."""
        return session_labels(self.dir(sid), kind)

    def strokes(self, sid: str) -> List[Dict[str, Any]]:
        """The drawing, with older field names folded onto the current ones."""
        return session_strokes(self.dir(sid))

    def finalize(self, sid: str) -> Dict[str, Any]:
        """Close the two process streams: nothing more is coming, so compress.

        Only the high-volume streams — `labels.jsonl` stays plain text because a
        teacher may still be grading weeks later.
        """
        out = {}
        for stream in ("strokes", "events"):
            log = JsonlLog(self.dir(sid) / f"{stream}.jsonl")
            before = log.path.stat().st_size if log.path.exists() else 0
            if log.compress():
                out[stream] = {"bytes": before, "gz_bytes": log.gz_path.stat().st_size}
        return out

    def _strokes_summary(self, sid: str) -> Dict[str, Any]:
        log = self.log(sid, "strokes")
        rows = log.read()
        return {
            "count": len(rows),
            "points": sum(len(r.get("points") or []) for r in rows),
            "tools": sorted({r.get("tool") for r in rows if r.get("tool")}),
            "colors": sorted({r.get("color") for r in rows if r.get("color")}),
            "last_t_ms": max((ev.stroke_end_ms(r) for r in rows), default=0),
        }

    # -- images ------------------------------------------------------------
    def add_snapshot(self, sid: str, png: bytes, elapsed_ms: int) -> str:
        """An intermediate frame. Off by default (`ARTQUEST_SNAPSHOT_INTERVAL=0`)
        because the log can regenerate any moment; kept for experiments that
        genuinely need frames, and stored beside the other deliberate ones."""
        meta = self.load(sid)
        idx = len(meta.get("snapshots", [])) + 1
        name = f"{idx:04d}_{elapsed_ms // 1000}s.png"
        d = self.dir(sid) / "checkpoints"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(png)
        meta.setdefault("snapshots", []).append({"file": f"checkpoints/{name}", "elapsed_ms": elapsed_ms, "at": now_iso()})
        meta.setdefault("counts", {})["snapshots"] = len(meta["snapshots"])
        self._write(sid, meta)
        return name

    # -- images ------------------------------------------------------------
    # Artwork(t) = replay(strokes[0:t], events[0:t]), so a frame is only worth
    # storing when it is an *experimental* landmark. `final.png` is the work;
    # the pre-feedback state is written only if a revision actually starts.
    # Before this, a session with no revision stored the same PNG three times.
    def save_phase_image(self, sid: str, phase: str, png: bytes) -> Path:
        final = self.dir(sid) / "final.png"
        # The work about to be replaced by a revision *is* the pre-feedback
        # state — the one frame a replay cannot tell you was an experimental
        # landmark. Freeze it here rather than storing a copy every submit.
        if phase == "after" and final.exists():
            self.save_checkpoint(sid, "before_feedback")
        final.write_bytes(png)
        return final

    def save_checkpoint(self, sid: str, name: str) -> Optional[Path]:
        """Freeze the current `final.png` as a named experimental landmark."""
        final = self.dir(sid) / "final.png"
        if not final.exists():
            return None
        d = self.dir(sid) / "checkpoints"
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"{name}.png"
        shutil.copyfile(final, dest)
        return dest

    # phase -> where that frame may be found, newest layout first
    _IMAGE_PATHS = {
        "before": ("checkpoints/before_feedback.png", "before.png", "final.png"),
        "after": ("final.png", "after.png"),
        "final": ("final.png", "after.png", "before.png"),
    }

    def read_image(self, sid: str, phase: str) -> Optional[bytes]:
        d = self.dir(sid)
        for name in self._IMAGE_PATHS.get(phase, (f"{phase}.png",)):
            p = d / name
            if p.exists():
                return p.read_bytes()
        return None

    # -- mutations ---------------------------------------------------------
    def update(self, sid: str, **fields: Any) -> Dict[str, Any]:
        meta = self.load(sid)
        meta.update(fields)
        self._write(sid, meta)
        return meta

    # -- 被选为优秀作品：先问，答了才算 --------------------------------
    # `share_consent` 管的是「这幅画可不可以被别人看见」，是画之前就冻结的条件。
    # 这里管的是另一件事：**这一张**被老师挑出来当优秀作品时，本人愿不愿意。
    # 两道闸都要过。老师的 pin 只产生一个 pending，不会自己变成展出。
    FEATURED_STATES = ("pending", "accepted", "declined")

    def propose_featured(self, sid: str, *, by: str = "", note: str = "") -> Dict[str, Any]:
        """A teacher picked this one. Nothing is shown yet — the child is asked."""
        meta = self.load(sid)
        cur = meta.get("featured") or {}
        if cur.get("state") in ("accepted", "declined"):
            return cur                      # 已经问过并答过了，不再骚扰
        rec = {"state": "pending", "by": by, "note": note, "proposed_at": now_iso()}
        meta["featured"] = rec
        self._write(sid, meta)
        self.add_server_event(sid, ev.FEATURED_PROPOSED, 0, {"by": by})
        return rec

    def answer_featured(self, sid: str, accept: bool) -> Dict[str, Any]:
        """The child's own answer. Declining is final until they change it here."""
        meta = self.load(sid)
        rec = dict(meta.get("featured") or {})
        rec["state"] = "accepted" if accept else "declined"
        rec["answered_at"] = now_iso()
        meta["featured"] = rec
        self._write(sid, meta)
        self.add_server_event(sid, ev.FEATURED_ACCEPTED if accept else ev.FEATURED_DECLINED, 0, {})
        return rec

    def update_task(self, sid: str, **fields: Any) -> Dict[str, Any]:
        """Merge into the frozen task block, re-reading first.

        `task` now holds the whole frozen definition, so writing back a copy
        captured before it was frozen would quietly drop the snapshot.
        """
        meta = self.load(sid)
        meta["task"] = {**(meta.get("task") or {}), **fields}
        self._write(sid, meta)
        return meta

    def mark_started(self, sid: str, at_iso: str = "") -> None:
        meta = self.load(sid)
        times = meta.setdefault("times", {})
        if not times.get("started_at"):
            times["started_at"] = at_iso or now_iso()
            self._write(sid, meta)

    def mark_ended(self, sid: str, duration_ms: Optional[int] = None) -> Dict[str, Any]:
        meta = self.load(sid)
        times = meta.setdefault("times", {})
        times["ended_at"] = now_iso()
        if duration_ms is not None:
            times["duration_ms"] = duration_ms
        self._write(sid, meta)
        return meta

    def self_report(self, sid: str) -> Optional[Dict[str, Any]]:
        """The child's own answers, wherever this session's layout keeps them."""
        return session_part(self.dir(sid), "self_report")

    def save_quality(self, sid: str, result: Dict[str, Any]) -> Dict[str, Any]:
        meta = self.load(sid)
        meta["qc"] = result
        self._write(sid, meta)
        return result

    def copy_reference(self, sid: str, quest: Dict[str, Any]) -> Optional[str]:
        """Keep the stimulus the child saw inside the session directory.

        The file in `static/refs/` will be replaced when a real stimulus lands;
        a session that points at a path is not self-contained, and the artwork
        would end up next to an image nobody showed this child.
        """
        ref = quest.get("reference") or {}
        url = (ref.get("file") or "").lstrip("/")
        if not url:
            return None
        src = config.BASE_DIR / url
        if not src.exists():
            return None
        dest_dir = self.dir(sid) / "reference"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copyfile(src, dest)
        return f"reference/{src.name}"

    def save_questionnaire(self, sid: str, answers: Dict[str, Any]) -> Dict[str, Any]:
        rec = dict(answers, session_id=sid, at=now_iso())
        self.update(sid, self_report=rec, questionnaire=rec)
        return rec


# ---------------------------------------------------------------------------
# Directory-level readers
# ---------------------------------------------------------------------------
# Tools and modules that hold a path rather than a store read a session through
# these, so the "new layout, else the older split one" rule lives in exactly one
# place. Nothing here ever writes: collected data is not rewritten to fit a
# newer shape, it is folded on the way out.
_PART_FILES = {
    "personalization": ("personalization.json",),
    "self_report": ("self_report.json", "questionnaire.json"),
    "qc": ("quality.json",),
}


def belongs_to(meta: Dict[str, Any], *, participant_id: str, anon_id: str,
          account_id: str, windows: Dict[str, str]) -> bool:
    """这条 session 算不算「我的」。

    三条，顺序就是优先级：

    1. **带账号的作品只归那个账号**。同一台 iPad 上换个孩子登录，
       上一个孩子的画不会因为设备相同就漏过去——这是账号存在的意义之一。
    2. 没有账号的作品，可以被**认领过这台设备**的账号收走，但只收
       认领时刻之前的（`windows`）。之后在同一台设备上无账号画的画不算，
       共用设备的教室里那是别人的。
    3. 都不沾边，就回到原来那两个 id：研究员代号、设备代号。
    """
    p = meta.get("participant")
    p = p if isinstance(p, dict) else {"participant_id": p or ""}
    owner = p.get("account_id") or ""
    if owner:
        return bool(account_id) and owner == account_id
    if account_id:
        until = windows.get(p.get("anon_id") or "")
        if until and (meta.get("created_at") or "") <= until:
            return True
    return bool((participant_id and p.get("participant_id") == participant_id)
                or (anon_id and p.get("anon_id") == anon_id))


def sid_of(meta: Dict[str, Any]) -> str:
    """A session's id, under either spelling (schema 1/2 also wrote `id`)."""
    return (meta or {}).get("session_id") or (meta or {}).get("id") or ""


def session_meta(d: Path) -> Dict[str, Any]:
    """`session.json` (schema 1 and 3) or `metadata.json` (schema 2)."""
    return read_json(Path(d) / "session.json") or read_json(Path(d) / "metadata.json") or {}


def session_part(d: Path, name: str) -> Optional[Dict[str, Any]]:
    """One of the small blocks that used to be its own file."""
    d = Path(d)
    rec = (session_meta(d) or {}).get(name)
    if rec:
        return rec
    for f in _PART_FILES.get(name, ()):
        rec = read_json(d / f)
        if rec:
            return rec
    return None


def session_task(d: Path) -> Dict[str, Any]:
    """The task definition as this child actually saw it."""
    task = (session_meta(d) or {}).get("task") or {}
    if task.get("frozen_at"):
        return task
    return read_json(Path(d) / "condition.json") or task


def session_events(d: Path) -> List[Dict[str, Any]]:
    return JsonlLog(Path(d) / "events.jsonl").read()


def session_strokes(d: Path) -> List[Dict[str, Any]]:
    return [ev.canonical_stroke(r) for r in JsonlLog(Path(d) / "strokes.jsonl").read()]


def session_feedback(d: Path) -> List[Dict[str, Any]]:
    """Every feedback shown, feedback-shaped.

    It is one of the events on the timeline now; older sessions had a file of
    its own. Either way a caller gets the flat record it always got.
    """
    d = Path(d)
    own = JsonlLog(d / "feedback.jsonl")
    if own.exists():
        return own.read()
    out = []
    for e in session_events(d):
        if ev.canonical(e.get("type", "")) != ev.FEEDBACK_SHOW:
            continue
        p = e.get("payload") or {}
        if p.get("feedback_id"):
            out.append({**p, "t_ms": e.get("t_ms", 0)})
    return out


def session_labels(d: Path, kind: str = "") -> List[Dict[str, Any]]:
    d, rows = Path(d), []
    for stream, tag in _LABEL_TYPE.items():
        own = JsonlLog(d / f"{stream}.jsonl")
        if own.exists():
            rows += [dict(r, type=r.get("type", tag)) for r in own.read()]
    merged = JsonlLog(d / "labels.jsonl")
    if merged.exists():
        rows += merged.read()
    return [r for r in rows if not kind or r.get("type") == kind]


def dataset_manifest(root: Optional[Path] = None) -> Dict[str, Any]:
    """One file at the top of `data/` saying what this dataset is.

    Counts are read back from the sessions rather than kept as running state:
    a manifest that can drift from the data it describes is worse than none.
    """
    root = Path(root or config.SESSIONS_DIR)
    counts = {"sessions": 0, "done": 0, "verified": 0, "withdrawn": 0,
              "strokes": 0, "points": 0, "events": 0, "labels": 0}
    schemas: Dict[str, int] = {}
    for d in sorted(root.iterdir()) if root.exists() else []:
        if not d.is_dir():
            continue
        m = session_meta(d)
        if not m:
            continue
        counts["sessions"] += 1
        sv = str(m.get("schema_version", 1))
        schemas[sv] = schemas.get(sv, 0) + 1
        if m.get("status") == "done":
            counts["done"] += 1
        if m.get("status") == "withdrawn":
            counts["withdrawn"] += 1
        if m.get("lifecycle") == "server_verified":
            counts["verified"] += 1
        c = m.get("counts") or {}
        for k in ("strokes", "points", "events"):
            counts[k] += int(c.get(k) or 0)
        counts["labels"] += len(session_labels(d))
    return {
        "dataset": "artquest",
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "generated_at": now_iso(),
        "counts": counts,
        "sessions_by_schema": schemas,
        "layout": {
            "session.json": "identity, frozen task, condition, device, canvas, timing, "
                            "personalisation, self-report, QC",
            "strokes.jsonl[.gz]": "one line per stroke: geometry + time + tool state; "
                                  "points are [x, y, dt_ms, pressure, tilt_x, tilt_y] "
                                  "in canvas pixels, dt from the stroke's t0_ms",
            "events.jsonl[.gz]": "every non-drawing operation, feedback included",
            "labels.jsonl": "human ground truth: teacher ratings + expert process spans",
            "final.png": "the last submitted work",
            "checkpoints/": "frames kept on purpose (before_feedback, and any snapshots)",
            "reference/": "the stimulus this child saw",
        },
        "note": "Older sessions keep the split layout they were recorded in; every "
                "reader in artquest/storage.py folds them onto this shape.",
    }
