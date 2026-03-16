from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

AppExecutionMode = Literal["service", "pipeline"]
InteractionAction = Literal["open_app", "run_pipeline", "clarify"]


class AppCatalogEntry(BaseModel):
    app_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    execution_mode: AppExecutionMode
    trigger_phrases: list[str] = Field(default_factory=list)
    blueprint_id: str = Field(..., min_length=1)
    version: str = "0.1.0"


class UserCommand(BaseModel):
    user_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InteractionDecision(BaseModel):
    action: InteractionAction
    app_id: str | None = None
    app_instance_id: str | None = None
    execution_mode: AppExecutionMode | None = None
    message: str
    matched_phrases: list[str] = Field(default_factory=list)
    pending_tasks: list[str] = Field(default_factory=list)
