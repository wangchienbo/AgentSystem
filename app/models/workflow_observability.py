from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.workflow_execution import WorkflowExecutionResult


WorkflowHealthStatus = Literal["healthy", "failing", "recovering", "unknown"]
WorkflowSeverity = Literal["info", "warning", "critical"]


class WorkflowRecoveryState(BaseModel):
    recovered: bool = False
    still_failing: bool = False
    resolved_failed_step_ids: list[str] = Field(default_factory=list)
    unchanged_failed_step_ids: list[str] = Field(default_factory=list)
    newly_failed_step_ids: list[str] = Field(default_factory=list)


class WorkflowRecoverySummary(BaseModel):
    workflow_id: str
    retried_at: str
    retry_of_completed_at: str | None = None
    recovered: bool = False
    still_failing: bool = False
    previous_failed_step_ids: list[str] = Field(default_factory=list)
    retried_failed_step_ids: list[str] = Field(default_factory=list)
    resolved_failed_step_ids: list[str] = Field(default_factory=list)
    unchanged_failed_step_ids: list[str] = Field(default_factory=list)
    newly_failed_step_ids: list[str] = Field(default_factory=list)


class WorkflowDiagnosticsSummary(BaseModel):
    latest_execution: WorkflowExecutionResult | None = None
    latest_failure: WorkflowExecutionResult | None = None
    latest_retry: WorkflowExecutionResult | None = None
    recovery_state: WorkflowRecoveryState | None = None


class WorkflowHealthSummary(BaseModel):
    health_status: WorkflowHealthStatus = "unknown"
    severity: WorkflowSeverity = "info"
    unresolved_failure_count: int = 0
    latest_failed_step_ids: list[str] = Field(default_factory=list)
    has_recent_retry: bool = False
    last_transition: str = "unknown"


class WorkflowTimelineEvent(BaseModel):
    app_instance_id: str
    workflow_id: str
    event_kind: Literal["failure", "retry", "recovery", "completed", "partial"]
    status: Literal["completed", "partial"]
    completed_at: str
    failed_step_ids: list[str] = Field(default_factory=list)
    summary: str
    retry_of_completed_at: str | None = None


class WorkflowPageMeta(BaseModel):
    returned_count: int = 0
    unresolved_count: int = 0
    has_more: bool = False
    window_since: str | None = None
    next_cursor: str | None = None


class WorkflowTimelinePage(BaseModel):
    items: list[WorkflowTimelineEvent] = Field(default_factory=list)
    meta: WorkflowPageMeta = Field(default_factory=WorkflowPageMeta)


class WorkflowHistoryPage(BaseModel):
    items: list[WorkflowExecutionResult] = Field(default_factory=list)
    meta: WorkflowPageMeta = Field(default_factory=WorkflowPageMeta)


class WorkflowObservabilityFilter(BaseModel):
    app_instance_id: str
    workflow_id: str | None = None
    failed_step_id: str | None = None
    limit: int | None = None
    unresolved_only: bool = False
    since: str | None = None
    cursor: str | None = None


class WorkflowStatsSummary(BaseModel):
    total_executions: int = 0
    total_failures: int = 0
    total_retries: int = 0
    total_recoveries: int = 0
    total_completed: int = 0
    total_partial_without_failed_steps: int = 0
    unresolved_executions: int = 0
    latest_event_at: str | None = None


class WorkflowDashboardSummary(BaseModel):
    overview: WorkflowOverview
    stats: WorkflowStatsSummary
    recent_timeline: WorkflowTimelinePage


class WorkflowOverview(BaseModel):
    diagnostics: WorkflowDiagnosticsSummary
    latest_recovery: WorkflowRecoverySummary | None = None
    health: WorkflowHealthSummary
