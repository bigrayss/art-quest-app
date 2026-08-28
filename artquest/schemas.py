"""Pydantic request/response models."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class Intent(BaseModel):
    emotion: str = Field(..., description="画前情绪")
    text: str = Field("", description="一句话创作意图")


class CreateSession(BaseModel):
    quest_id: str
    intent: Intent
    participant: str = Field("", description="可选：参与者代号（不要用真名）")


class DrawEvent(BaseModel):
    t_ms: int
    type: str
    detail: Optional[Dict[str, Any]] = None


class Snapshot(BaseModel):
    image: str = Field(..., description="canvas dataURL (image/png;base64)")
    elapsed_ms: int
    events: List[DrawEvent] = []


class Submit(BaseModel):
    image: str
    elapsed_ms: int
    phase: Literal["before", "after"]
    events: List[DrawEvent] = []


class Finalize(BaseModel):
    """Finish the session without a revision (after == before)."""
    elapsed_ms: int
    events: List[DrawEvent] = []
