from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class EventRecord(BaseModel):
    event_id: str = Field(..., min_length=1)
    event_name: str = Field(..., min_length=1)
    source: str = Field(default="system")
    app_instance_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventSubscription(BaseModel):
    subscription_id: str = Field(..., min_length=1)
    event_name: str = Field(..., min_length=1)
    schedule_id: str | None = None
    app_instance_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventPublishResult(BaseModel):
    event: EventRecord
    triggered_schedule_ids: list[str] = Field(default_factory=list)
    triggered_app_ids: list[str] = Field(default_factory=list)
