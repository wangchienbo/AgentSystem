from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.app_instance import AppStatus

RuntimeEventType = Literal[
    "create",
    "validate",
    "compile",
    "install",
    "start",
    "pause",
    "resume",
    "stop",
    "fail",
    "upgrade",
    "archive",
    "healthcheck",
    "checkpoint",
]


class RuntimeCheckpoint(BaseModel):
    checkpoint_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    status: AppStatus
    pending_tasks: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LifecycleEvent(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    event_type: RuntimeEventType
    from_status: AppStatus
    to_status: AppStatus
    reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RuntimeLease(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    status: AppStatus
    health: Literal["healthy", "degraded", "failed"] = "healthy"
    last_heartbeat_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    restart_count: int = 0


class LifecycleTransitionResult(BaseModel):
    app_instance_id: str
    previous_status: AppStatus
    current_status: AppStatus
    event: RuntimeEventType
    recorded_events: int


class RuntimeOverview(BaseModel):
    app_instance: dict[str, str]
    lease: RuntimeLease | None = None
    latest_checkpoint: RuntimeCheckpoint | None = None
    pending_tasks: list[str] = Field(default_factory=list)
