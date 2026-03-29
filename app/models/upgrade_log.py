from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class UpgradeLogEvent(BaseModel):
    event_id: str = Field(..., min_length=1)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1)
    app_id: str | None = None
    skill_id: str | None = None
    agent_id: str | None = None
    interaction_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    extension_payload: dict[str, Any] | None = None
