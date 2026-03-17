from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

ContextStatus = Literal["active", "paused", "archived"]


class AppContextEntry(BaseModel):
    entry_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    section: Literal["facts", "artifacts", "decisions", "questions", "constraints", "open_loops"]
    key: str = Field(..., min_length=1)
    value: dict | list | str | int | float | bool | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppSharedContext(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    app_name: str = Field(..., min_length=1)
    description: str = Field(default="")
    status: ContextStatus = "active"
    current_goal: str = Field(default="")
    current_stage: str = Field(default="")
    entries: list[AppContextEntry] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
