"""Pydantic request/response models."""
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from .scoring.base import DIM_KEYS, SCALE_MAX


class Intent(BaseModel):
    emotion: str = Field(..., description="画前情绪")
    text: str = Field("", description="一句话创作意图")


class Participant(BaseModel):
    """Two ids, both anonymous: a device-local one, plus a researcher code."""
    anon_id: str = Field("", description="设备本地生成的匿名 id，日常也能跨任务对齐")
    participant_id: str = Field("", description="研究员分配的代号，如 P007（不要用真名）")
    label: str = ""


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

    `points` are `[x, y, dt_ms, pressure, tiltX, tiltY]` in canvas pixel space,
    `dt_ms` relative to `t_start_ms`. Zoom and pan never enter these numbers —
    they are a view transform, so a stroke drawn at 4x lands in the same
    coordinate space as one drawn at 1x and replay stays exact. `zoom` records
    what the child could see while drawing it, which is a different question.

    Raw only: no speed/length/hesitation is computed here, that belongs in
    offline analysis.
    """
    seq: int
    stroke_id: str = ""
    phase: Literal["before", "after"] = "before"
    t_start_ms: int = 0
    t_end_ms: int = 0
    tool: str = ""
    color: str = ""
    size: float = 0
    opacity: float = 1.0
    erase: bool = False
    pointer_type: str = ""
    zoom: float = 1.0
    points: List[List[float]] = []


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


class Questionnaire(BaseModel):
    """Light self-report: a little ground truth for the behavioural data."""
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    confidence: Optional[int] = Field(None, ge=1, le=5)
    enjoyment: Optional[int] = Field(None, ge=1, le=5)
    hardest_part: str = ""
    free_text: str = ""
    t_ms: int = Field(0, description="会话计时，保证事件在统一时间线上有精确位置")


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
    """A human (teacher/self) feedback entry, alongside the AI ones."""
    source: Literal["teacher", "self", "ai"] = "teacher"
    feedback_type: str = "text"
    text: str
    t_ms: int = 0
    phase: Literal["before", "after"] = "before"
    target_region: Optional[TargetRegion] = None


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
