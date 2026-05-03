from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PendingTaskStatus = Literal[
    "drafted",
    "pending_input",
    "ready_to_execute",
    "executing",
    "completed",
    "blocked",
    "abandoned",
]


class PendingTaskRecord(BaseModel):
    task_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    session_id: str | None = None
    intent: str = Field(..., min_length=1)
    status: PendingTaskStatus = "pending_input"
    draft_payload: dict[str, Any] = Field(default_factory=dict)
    target_ref: dict[str, Any] = Field(default_factory=dict)
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    next_recommended_action: dict[str, Any] | None = None
    last_user_message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
