from __future__ import annotations

from datetime import datetime
from typing import Iterable, Literal

from app.models.workflow_execution import WorkflowExecutionResult
from app.models.workflow_observability import WorkflowObservabilityFilter, WorkflowRecoveryState

HealthStatus = Literal["healthy", "failing", "recovering", "unknown"]
HealthSeverity = Literal["info", "warning", "critical"]

HEALTH_RULES: tuple[dict[str, str], ...] = (
    {"health_status": "recovering", "severity": "warning", "last_transition": "failure->recovered"},
    {"health_status": "failing", "severity": "critical", "last_transition": "failure"},
    {"health_status": "healthy", "severity": "info", "last_transition": "completed"},
    {"health_status": "unknown", "severity": "info", "last_transition": "partial-without-failed-steps"},
)


def apply_history_filters(
    history: list[WorkflowExecutionResult],
    filters: WorkflowObservabilityFilter,
    matches_failed_step,
    is_unresolved,
) -> list[WorkflowExecutionResult]:
    items = list(history)
    if filters.workflow_id is not None:
        items = [item for item in items if item.workflow_id == filters.workflow_id]
    if filters.failed_step_id is not None:
        items = [item for item in items if matches_failed_step(item, filters.failed_step_id)]
    if filters.unresolved_only:
        items = [item for item in items if is_unresolved(item)]
    if filters.since is not None:
        since_dt = datetime.fromisoformat(filters.since.replace("Z", "+00:00"))
        items = [item for item in items if item.completed_at >= since_dt]
    items = sorted(items, key=lambda item: item.completed_at, reverse=True)
    if filters.cursor is not None:
        cursor_dt = datetime.fromisoformat(filters.cursor.replace("Z", "+00:00"))
        items = [item for item in items if item.completed_at < cursor_dt]
    if filters.limit is not None:
        items = items[: filters.limit]
    return items


def count_unresolved_failures(recovery_state: WorkflowRecoveryState | None) -> int:
    if recovery_state is None:
        return 0
    return len(recovery_state.unchanged_failed_step_ids) + len(recovery_state.newly_failed_step_ids)


def classify_health(
    latest_execution: WorkflowExecutionResult,
    recovery_state: WorkflowRecoveryState | None,
    has_recent_retry: bool,
) -> tuple[HealthStatus, HealthSeverity, str]:
    latest_failed_step_ids = list(latest_execution.failed_step_ids)
    if recovery_state is not None and recovery_state.recovered:
        rule = HEALTH_RULES[0]
        return rule["health_status"], rule["severity"], rule["last_transition"]
    if latest_execution.status == "partial" and latest_failed_step_ids:
        rule = HEALTH_RULES[1]
        last_transition = "failure->retry-partial" if has_recent_retry else rule["last_transition"]
        return rule["health_status"], rule["severity"], last_transition
    if latest_execution.status == "completed":
        rule = HEALTH_RULES[2]
        return rule["health_status"], rule["severity"], rule["last_transition"]
    rule = HEALTH_RULES[3]
    return rule["health_status"], rule["severity"], rule["last_transition"]


def iter_retry_step_ids(comparison) -> Iterable[str]:
    yield from comparison.previous_failed_step_ids
    yield from comparison.retried_failed_step_ids
    yield from comparison.resolved_failed_step_ids
    yield from comparison.unchanged_failed_step_ids
    yield from comparison.newly_failed_step_ids
