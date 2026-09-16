"""Pydantic request/response models."""
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from .scoring.base import DIM_KEYS, SCALE_MAX


class Intent(BaseModel):
    emotion: str = Field(..., description="画前情绪")
    text: str = Field("", description="一句话创作意图")


class Participant(BaseModel):
    """Two ids, both anonymous: a device-local one, plus a researcher code."""
    anon_id: str = Field("", description="设备本地生成的匿名 id，日常也能跨任务对齐")
    participant_id: str = Field("", description="研究员分配的代号，如 P007（不要用真名）")
    label: str = ""
    # 孩子给创作伙伴起的名字。存下来是因为「有没有给它起名」本身就是投入程度的信号
    buddy_name: str = Field("", max_length=16, description="孩子给创作伙伴起的名字")


class Device(BaseModel):
    ua: str = ""
    platform: str = ""
    screen: List[int] = []
    viewport: List[int] = []
    dpr: float = 1.0
    pointer_types: List[str] = []
    timezone: str = ""
    language: str = ""


class Canvas(BaseModel):
    """Canvas geometry, required to replay strokes faithfully."""
    width: int = 0
    height: int = 0
    css_width: float = 0
    css_height: float = 0


class StudyContext(BaseModel):
    active: bool = False
    study_id: str = ""
    protocol_id: str = ""
    group: str = ""
    order_index: Optional[int] = None
    sequence_id: str = ""


class CreateSession(BaseModel):
    quest_id: str = ""
    task_id: str = ""  # research-facing alias for quest_id
    intent: Intent
    participant: Union[Participant, str] = Participant()
    condition: Dict[str, Any] = {}
    device: Device = Device()
    canvas: Canvas = Canvas()
    study: StudyContext = StudyContext()

    def task(self) -> str:
        return self.quest_id or self.task_id

    def participant_dict(self) -> Dict[str, Any]:
        if isinstance(self.participant, str):  # legacy free-text field
            return {"anon_id": "", "participant_id": "", "label": self.participant}
        return self.participant.model_dump()


class DrawEvent(BaseModel):
    """One line of the append-only operation log."""
    seq: Optional[int] = None
    t_ms: int = 0
    type: str
    payload: Optional[Dict[str, Any]] = None
    detail: Optional[Dict[str, Any]] = None  # accepted from older clients

    def record(self) -> Dict[str, Any]:
        return {"seq": self.seq, "t_ms": self.t_ms, "type": self.type,
                "payload": self.payload if self.payload is not None else self.detail}


class Stroke(BaseModel):
    """One stroke with its sampled points — the core process datum.

        geometry + time + tool state, and nothing else

    `points` are `[x, y, dt_ms, pressure, tiltX, tiltY]` in canvas pixel space,
    `dt_ms` counted from `t0_ms`; absolute time is `times.started_at + t0_ms + dt`,
    so there is one clock and no record carries a second one. Anything derivable
    is left out: the stroke ends at `t0_ms + points[-1][2]`, and speed, length
    and hesitation belong to offline analysis.

    `pressure`/`tilt` are `null` when the pointer does not measure them, and the
    two `*_supported` flags say *why* — no sensor, as against a sensor that read
    nothing. Zoom and pan never enter the coordinates (they are a view
    transform, so a stroke drawn at 4x lands where a 1x one would and replay
    stays exact); `zoom` records what the child could see while drawing it,
    which is a different question and not recoverable from the numbers.

    `t_start_ms` / `pointer_type` / `erase` are the pre-schema-3 spellings and
    still accepted, so a client that has not reloaded keeps working.
    """
    model_config = {"populate_by_name": True}

    seq: int
    stroke_id: str = ""
    phase: Literal["before", "after"] = "before"
    op: Literal["draw", "erase"] = "draw"
    t0_ms: int = Field(0, validation_alias=AliasChoices("t0_ms", "t_start_ms"))
    tool: str = ""
    color: str = ""
    size: float = 0
    opacity: float = 1.0
    pointer: str = Field("", validation_alias=AliasChoices("pointer", "pointer_type"))
    pressure_supported: bool = False
    tilt_supported: bool = False
    zoom: float = 1.0
    # `None` in a slot means the device does not measure that channel — a mouse
    # reports a constant 0.5 pressure, which is not a reading
    points: List[List[Optional[float]]] = []

    @model_validator(mode="before")
    @classmethod
    def _fold_erase(cls, data):
        """`erase: true` was how an eraser stroke used to be spelled."""
        if isinstance(data, dict) and "op" not in data and data.get("erase"):
            data = dict(data, op="erase")
        return data


class LogBatch(BaseModel):
    """A buffered batch from the client; safe to re-send after a lost connection."""
    events: List[DrawEvent] = []
    strokes: List[Stroke] = []
    pending: int = Field(0, description="records still queued locally on the client")


class Snapshot(BaseModel):
    image: str = Field(..., description="canvas dataURL (image/png;base64)")
    elapsed_ms: int
    events: List[DrawEvent] = []


class Submit(BaseModel):
    image: str
    elapsed_ms: int
    phase: Literal["before", "after"]
    events: List[DrawEvent] = []
    strokes: List[Stroke] = []
    pending: int = 0


class Finalize(BaseModel):
    """Finish the session without a revision (after == before)."""
    elapsed_ms: int
    events: List[DrawEvent] = []
    strokes: List[Stroke] = []
    pending: int = 0


# What a child can pick as "the hardest part". A fixed set makes the answer
# comparable across tasks and children; free text stays available beside it,
# because a closed list that fits nobody is worse than no answer.
HARDEST_PARTS = [
    ("idea", "想不出要画什么"),
    ("shape", "形状画不准"),
    ("proportion", "大小和比例"),
    ("color", "颜色"),
    ("layout", "画面怎么安排"),
    ("line", "线条"),
    ("time", "时间不够"),
    ("none", "没有特别难的"),
    ("other", "其他"),
]
HARDEST_PART_KEYS = [k for k, _ in HARDEST_PARTS]


class EarnedBadges(BaseModel):
    """What the client's badge rules lit for this session.

    Stored with the rule-set `version` they were earned under: tightening a rule
    later must not retroactively take a badge off a child who already had it.
    """
    earned: List[str] = []
    offered: List[str] = []
    version: str = ""


class Abandon(BaseModel):
    """Backing out of a task before submitting it."""
    elapsed_ms: int = 0
    reason: Literal["wrong_task", "restart", "other"] = "wrong_task"
    events: List[DrawEvent] = []
    strokes: List[Stroke] = []
    pending: int = 0


class Questionnaire(BaseModel):
    """Light self-report: a little ground truth for the behavioural data.

    Two or three questions, at the end, never mid-task.
    """
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    confidence: Optional[int] = Field(None, ge=1, le=5)
    enjoyment: Optional[int] = Field(None, ge=1, le=5)
    # the closed answer, comparable across tasks…
    hardest_part_choice: Optional[str] = None
    # …and the child's own words, which is also what older sessions stored here
    hardest_part: str = ""
    free_text: str = ""
    t_ms: int = Field(0, description="会话计时，保证事件在统一时间线上有精确位置")

    @field_validator("hardest_part_choice")
    @classmethod
    def _known_choice(cls, v):
        if v and v not in HARDEST_PART_KEYS:
            raise ValueError(f"unknown hardest_part: {v!r}")
        return v


# Smaller than this and the numbers are fractions of the canvas, not pixels.
MIN_REGION_PX = 2.0


class TargetRegion(BaseModel):
    """Where on the canvas a piece of feedback points.

    In **canvas pixel space** — the same coordinates strokes are logged in — so
    "did the child then work where the feedback pointed?" is a number the
    analysis can compute, not a reading exercise. A free-form dict here would
    let a future teacher tool put anything in the field and quietly break that.

    coords: rect `[x, y, w, h]` · point `[x, y, radius]` · poly `[x1, y1, x2, y2, …]`
    """
    shape: Literal["rect", "point", "poly"] = "rect"
    coords: List[float]
    label: str = ""
    space: Literal["canvas"] = "canvas"

    @field_validator("coords")
    @classmethod
    def _shape_fits(cls, v, info):
        shape = (info.data or {}).get("shape", "rect")
        need = {"rect": 4, "point": 3}
        if shape in need and len(v) != need[shape]:
            raise ValueError(f"{shape} needs {need[shape]} coords, got {len(v)}")
        if shape == "poly" and (len(v) < 6 or len(v) % 2):
            raise ValueError("poly needs an even number of coords, at least 3 points")
        # A sub-pixel region is not a small region, it is fractional coordinates
        # that were never converted — the one mistake this field invites, and one
        # that would otherwise silently produce a region no stroke can fall in.
        if shape == "rect" and (v[2] < MIN_REGION_PX or v[3] < MIN_REGION_PX):
            raise ValueError(f"rect is {v[2]}x{v[3]}; regions are in canvas pixels, "
                             f"at least {MIN_REGION_PX}px a side (fractions of the canvas are not accepted)")
        if shape == "point" and v[2] < MIN_REGION_PX:
            raise ValueError(f"point radius {v[2]} is below {MIN_REGION_PX}px; regions are in canvas pixels")
        return v


class FeedbackIn(BaseModel):
    """A feedback entry — teacher, the child's own, or a model's.

    `trigger` / `model` / `prompt_version` are carried even when no AI is
    running, so a later model-generated intervention drops into the same rows:
    which event caused it, which model wrote it, and under which prompt.
    """
    source: Literal["teacher", "self", "ai"] = "teacher"
    feedback_type: str = "text"
    text: str
    t_ms: int = 0
    phase: Literal["before", "after"] = "before"
    target_region: Optional[TargetRegion] = None
    trigger: str = Field("", description="什么引发了这条反馈：submit / teacher / auto / …")
    model: str = Field("", description="生成它的模型（人写的留空）")
    prompt_version: str = Field("", description="生成它所用 prompt 的版本")


PROCESS_LABELS = ("planning", "exploration", "revision", "organization", "turning_point")


class Annotation(BaseModel):
    """An expert marking a *span* of the replay, never a single stroke.

    Stroke-by-stroke labelling is unaffordable and unreliable; what a rater can
    actually see in a replay is a stretch of behaviour, so the unit is a span on
    the same `t_ms` timeline everything else uses.
    """
    rater_id: str = Field("", description="伪匿名标注者编号，不要用真名")
    label: Literal[PROCESS_LABELS] = "planning"
    t_start_ms: int = Field(0, ge=0)
    t_end_ms: int = Field(0, ge=0)
    confidence: Optional[int] = Field(None, ge=1, le=5)
    note: str = ""

    @field_validator("t_end_ms")
    @classmethod
    def _ordered(cls, v, info):
        start = (info.data or {}).get("t_start_ms", 0)
        if v < start:
            raise ValueError("t_end_ms must not precede t_start_ms")
        return v


class FeaturedAnswer(BaseModel):
    """孩子对「你的画被选为优秀作品」的答复。

    被挑中不等于被展出：`share_consent` 管的是「这幅画可不可以被别人看见」，
    这里管的是**这一张**要不要挂出去，由本人说了算，而且随时可以改回来。
    """
    accept: bool


class Curate(BaseModel):
    """每天挑一批挂出来。挑完只是提议，等本人答应——没有一个参数是关于「好坏」的。"""
    k: int = Field(6, ge=1, le=24, description="这一轮最多提议几张")
    since: str = Field("", description="只考虑这个 ISO 时间之后完成的作品；空=全部还没被挑过的")
    cooldown_days: int = Field(7, ge=0, le=365,
                               description="同一个孩子隔多少天才会再被挑一次")


class Rating(BaseModel):
    """Someone other than the child rating the artwork.

    Append-only and carrying a `rater_id`, so two teachers rating the same
    session is the normal case rather than an overwrite — inter-rater agreement
    is something a dataset has to be able to report.
    """
    source: Literal["teacher", "expert", "peer"] = "teacher"
    rater_id: str = Field("", description="伪匿名评分者编号，不要用真名")
    phase: Literal["before", "after"] = "after"
    overall: Optional[int] = Field(None, ge=1, le=SCALE_MAX)
    dims: Dict[str, int] = Field({}, description="可选的 9 维打分，与模型同一量表")
    note: str = ""
    t_ms: int = 0
    featured: bool = Field(False, description="老师选它给大家看——人的决定，不是排名函数")

    @field_validator("dims")
    @classmethod
    def _known_dims(cls, v):
        bad = sorted(set(v) - set(DIM_KEYS))
        if bad:
            raise ValueError(f"unknown dimensions: {bad}")
        out_of_range = {k: s for k, s in v.items() if not 1 <= s <= SCALE_MAX}
        if out_of_range:
            raise ValueError(f"scores must be 1–{SCALE_MAX}: {out_of_range}")
        return v


class StudyAssign(BaseModel):
    participant_id: str = ""
    anon_id: str = ""
    group: str = ""
