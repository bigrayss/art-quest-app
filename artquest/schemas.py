"""Pydantic request/response models."""
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


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
    `dt_ms` relative to `t_start_ms`. Raw only: no speed/length/hesitation is
    computed here, that belongs in offline analysis.
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


class FeedbackIn(BaseModel):
    """A human (teacher/self) feedback entry, alongside the AI ones."""
    source: Literal["teacher", "self", "ai"] = "teacher"
    feedback_type: str = "text"
    text: str
    t_ms: int = 0
    phase: Literal["before", "after"] = "before"
    target_region: Optional[Dict[str, Any]] = None


class StudyAssign(BaseModel):
    participant_id: str = ""
    anon_id: str = ""
    group: str = ""
