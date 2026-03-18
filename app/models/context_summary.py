from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Any

from pydantic import BaseModel, Field

ContextLayer = Literal["working_set", "summary", "detail"]


class ContextSummary(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    layer: ContextLayer = "summary"
    current_goal: str = ""
    current_stage: str = ""
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_loops: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    detail_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
