from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

ScheduleTriggerType = Literal["interval", "event"]
ScheduleStatus = Literal["active", "paused", "disabled"]
SupervisorState = Literal["healthy", "restart_pending", "circuit_open"]


class ScheduleRecord(BaseModel):
    schedule_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    trigger_type: ScheduleTriggerType
    task_name: str = Field(..., min_length=1)
    interval_seconds: int | None = Field(default=None, ge=1)
    event_name: str | None = None
    status: ScheduleStatus = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_triggered_at: datetime | None = None


class ScheduleTriggerResult(BaseModel):
    schedule_id: str
    app_instance_id: str
    task_name: str
    triggered: bool
    reason: str = ""
    pending_tasks: list[str] = Field(default_factory=list)


class SupervisionPolicy(BaseModel):
    policy_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    max_restart_attempts: int = Field(default=3, ge=0)
    restart_on_failure: bool = True
    open_circuit_after_failures: int = Field(default=3, ge=1)


class SupervisionStatus(BaseModel):
    app_instance_id: str
    state: SupervisorState = "healthy"
    failure_count: int = 0
    restart_attempts: int = 0
    last_failure_reason: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SupervisionActionResult(BaseModel):
    app_instance_id: str
    action: Literal["observe_failure", "reset", "attempt_restart"]
    state: SupervisorState
    failure_count: int
    restart_attempts: int
    message: str = ""
