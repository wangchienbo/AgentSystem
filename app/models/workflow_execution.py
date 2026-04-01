from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Any

from pydantic import BaseModel, Field

WorkflowStepStatus = Literal["completed", "skipped", "failed", "paused_for_human", "waiting_for_event", "blocked_by_policy"]


class WorkflowStepExecution(BaseModel):
    step_id: str = Field(..., min_length=1)
    ref: str = Field(..., min_length=1)
    kind: str = Field(..., min_length=1)
    status: WorkflowStepStatus
    detail: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class WorkflowRetryComparison(BaseModel):
    previous_status: Literal["completed", "partial", "paused_for_human", "waiting_for_event", "blocked_by_policy"]
    retried_status: Literal["completed", "partial", "paused_for_human", "waiting_for_event", "blocked_by_policy"]
    previous_failed_step_ids: list[str] = Field(default_factory=list)
    retried_failed_step_ids: list[str] = Field(default_factory=list)
    resolved_failed_step_ids: list[str] = Field(default_factory=list)
    newly_failed_step_ids: list[str] = Field(default_factory=list)
    unchanged_failed_step_ids: list[str] = Field(default_factory=list)


class WorkflowExecutionResult(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    blueprint_id: str = Field(..., min_length=1)
    workflow_id: str = Field(..., min_length=1)
    trigger: str = Field(default="manual")
    status: Literal["completed", "partial", "paused_for_human", "waiting_for_event", "blocked_by_policy"] = "completed"
    outputs: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepExecution] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    failed_step_ids: list[str] = Field(default_factory=list)
    unresolved_step_ids: list[str] = Field(default_factory=list)
    blocked_step_ids: list[str] = Field(default_factory=list)
    waiting_step_ids: list[str] = Field(default_factory=list)
    pause_step_ids: list[str] = Field(default_factory=list)
    retry_of_completed_at: datetime | None = None
    retry_comparison: WorkflowRetryComparison | None = None
