from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class DemonstrationRecord(BaseModel):
    demonstration_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    steps: list[str] = Field(default_factory=list)
    observed_inputs: list[str] = Field(default_factory=list)
    observed_outputs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
