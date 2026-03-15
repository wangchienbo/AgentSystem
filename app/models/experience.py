from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

ExperienceSource = Literal["document", "demonstration", "runtime", "human_note"]


class ExperienceRecord(BaseModel):
    experience_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    source: ExperienceSource
    tags: list[str] = Field(default_factory=list)
    related_skills: list[str] = Field(default_factory=list)
    related_apps: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
