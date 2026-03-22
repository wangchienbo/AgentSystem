from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable, Literal

from app.models.workflow_execution import WorkflowExecutionResult
from app.models.workflow_observability import (
    WorkflowDiagnosticsSummary,
    WorkflowHealthSummary,
    WorkflowOverview,
    WorkflowRecoveryState,
    WorkflowRecoverySummary,
    WorkflowTimelineEvent,
    WorkflowTimelinePage,
)


HealthStatus = Literal["healthy", "failing", "recovering", "unknown"]
HealthSeverity = Literal["info", "warning", "critical"]


class WorkflowObservabilityService:
    _HEALTH_RULES: tuple[dict[str, str], ...] = (
        {"health_status": "recovering", "severity": "warning", "last_transition": "failure->recovered"},
        {"health_status": "failing", "severity": "critical", "last_transition": "failure"},
        {"health_status": "healthy", "severity": "info", "last_transition": "completed"},
        {"health_status": "unknown", "severity": "info", "last_transition": "partial-without-failed-steps"},
    )
    def __init__(self, workflow_executor) -> None:
        self._workflow_executor = workflow_executor

    def filter_history(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
        limit: int | None = None,
        unresolved_only: bool = False,
        since: str | None = None,
        cursor: str | None = None,
    ) -> list[WorkflowExecutionResult]:
        history = self._workflow_executor.list_history(app_instance_id)
        if workflow_id is not None:
            history = [item for item in history if item.workflow_id == workflow_id]
        if failed_step_id is not None:
            history = [item for item in history if self._matches_failed_step(item, failed_step_id)]
        if unresolved_only:
            history = [item for item in history if self._is_unresolved(item)]
        if since is not None:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            history = [item for item in history if item.completed_at >= since_dt]
        history = sorted(history, key=lambda item: item.completed_at, reverse=True)
        if cursor is not None:
            cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            history = [item for item in history if item.completed_at < cursor_dt]
        if limit is not None:
            history = history[:limit]
        return history

    def get_diagnostics_summary(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
    ) -> WorkflowDiagnosticsSummary:
        history = self.filter_history(app_instance_id, workflow_id=workflow_id, failed_step_id=failed_step_id)
        latest_execution = max(history, key=lambda item: item.completed_at) if history else None
        failures = [item for item in history if item.status == "partial" and item.failed_step_ids]
        latest_failure = max(failures, key=lambda item: item.completed_at) if failures else None
        retries = [item for item in history if item.retry_comparison is not None]
        latest_retry = max(retries, key=lambda item: item.completed_at) if retries else None
        recovery_state = None
        if latest_retry is not None and latest_retry.retry_comparison is not None:
            comparison = latest_retry.retry_comparison
            recovery_state = WorkflowRecoveryState(
                recovered=comparison.previous_status == "partial" and comparison.retried_status == "completed",
                still_failing=comparison.retried_status == "partial",
                resolved_failed_step_ids=list(comparison.resolved_failed_step_ids),
                unchanged_failed_step_ids=list(comparison.unchanged_failed_step_ids),
                newly_failed_step_ids=list(comparison.newly_failed_step_ids),
            )
        return WorkflowDiagnosticsSummary(
            latest_execution=latest_execution,
            latest_failure=latest_failure,
            latest_retry=latest_retry,
            recovery_state=recovery_state,
        )

    def get_latest_recovery_summary(self, app_instance_id: str, workflow_id: str | None = None) -> WorkflowRecoverySummary | None:
        history = self.filter_history(app_instance_id, workflow_id=workflow_id)
        retries = [item for item in history if item.retry_comparison is not None]
        latest_retry = max(retries, key=lambda item: item.completed_at) if retries else None
        if latest_retry is None or latest_retry.retry_comparison is None:
            return None
        comparison = latest_retry.retry_comparison
        return WorkflowRecoverySummary(
            workflow_id=latest_retry.workflow_id,
            retried_at=latest_retry.completed_at.isoformat(),
            retry_of_completed_at=None if latest_retry.retry_of_completed_at is None else latest_retry.retry_of_completed_at.isoformat(),
            recovered=comparison.previous_status == "partial" and comparison.retried_status == "completed",
            still_failing=comparison.retried_status == "partial",
            previous_failed_step_ids=list(comparison.previous_failed_step_ids),
            retried_failed_step_ids=list(comparison.retried_failed_step_ids),
            resolved_failed_step_ids=list(comparison.resolved_failed_step_ids),
            unchanged_failed_step_ids=list(comparison.unchanged_failed_step_ids),
            newly_failed_step_ids=list(comparison.newly_failed_step_ids),
        )

    def get_health_summary(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
    ) -> WorkflowHealthSummary:
        diagnostics = self.get_diagnostics_summary(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
        )
        latest_execution = diagnostics.latest_execution
        latest_retry = diagnostics.latest_retry
        recovery_state = diagnostics.recovery_state

        if latest_execution is None:
            return WorkflowHealthSummary()

        unresolved_failure_count = self._count_unresolved_failures(recovery_state)
        latest_failed_step_ids = list(latest_execution.failed_step_ids)
        has_recent_retry = latest_retry is not None
        health_status, severity, last_transition = self._classify_health(
            latest_execution=latest_execution,
            recovery_state=recovery_state,
            has_recent_retry=has_recent_retry,
        )

        return WorkflowHealthSummary(
            health_status=health_status,
            severity=severity,
            unresolved_failure_count=unresolved_failure_count,
            latest_failed_step_ids=latest_failed_step_ids,
            has_recent_retry=has_recent_retry,
            last_transition=last_transition,
        )

    def get_overview(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
    ) -> WorkflowOverview:
        diagnostics = self.get_diagnostics_summary(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
        )
        latest_recovery = self.get_latest_recovery_summary(app_instance_id=app_instance_id, workflow_id=workflow_id)
        health = self.get_health_summary(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
        )
        return WorkflowOverview(
            diagnostics=diagnostics,
            latest_recovery=latest_recovery,
            health=health,
        )

    def list_observability_history(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
        limit: int | None = None,
        unresolved_only: bool = False,
        since: str | None = None,
        cursor: str | None = None,
    ) -> list[WorkflowExecutionResult]:
        return self.filter_history(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
            limit=limit,
            unresolved_only=unresolved_only,
            since=since,
            cursor=cursor,
        )

    def list_timeline_events(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
        limit: int | None = None,
        unresolved_only: bool = False,
        since: str | None = None,
        cursor: str | None = None,
    ) -> WorkflowTimelinePage:
        history = self.list_observability_history(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
            limit=limit,
            unresolved_only=unresolved_only,
            since=since,
            cursor=cursor,
        )
        items = [self._to_timeline_event(item) for item in history]
        next_cursor = items[-1].completed_at if limit is not None and len(items) == limit else None
        return WorkflowTimelinePage(items=items, next_cursor=next_cursor)

    def _matches_failed_step(self, item: WorkflowExecutionResult, failed_step_id: str) -> bool:
        if failed_step_id in item.failed_step_ids:
            return True
        comparison = item.retry_comparison
        if comparison is None:
            return False
        return failed_step_id in self._iter_retry_step_ids(comparison)

    def _to_timeline_event(self, item: WorkflowExecutionResult) -> WorkflowTimelineEvent:
        comparison = item.retry_comparison
        event_kind = self._classify_timeline_event_kind(item)
        return WorkflowTimelineEvent(
            app_instance_id=item.app_instance_id,
            workflow_id=item.workflow_id,
            event_kind=event_kind,
            status=item.status,
            completed_at=item.completed_at.isoformat(),
            failed_step_ids=list(item.failed_step_ids),
            summary=self._build_timeline_summary(item, event_kind),
            retry_of_completed_at=None if item.retry_of_completed_at is None else item.retry_of_completed_at.isoformat(),
        )

    def _is_unresolved(self, item: WorkflowExecutionResult) -> bool:
        if item.status == "partial" and item.failed_step_ids:
            return True
        comparison = item.retry_comparison
        if comparison is None:
            return False
        return comparison.retried_status == "partial" and bool(
            comparison.unchanged_failed_step_ids or comparison.newly_failed_step_ids
        )

    def _classify_timeline_event_kind(self, item: WorkflowExecutionResult) -> Literal["failure", "retry", "recovery", "completed", "partial"]:
        comparison = item.retry_comparison
        if comparison is not None and comparison.previous_status == "partial" and comparison.retried_status == "completed":
            return "recovery"
        if comparison is not None:
            return "retry"
        if item.status == "partial" and item.failed_step_ids:
            return "failure"
        if item.status == "completed":
            return "completed"
        return "partial"

    def _build_timeline_summary(self, item: WorkflowExecutionResult, event_kind: str) -> str:
        if event_kind == "recovery":
            resolved = item.retry_comparison.resolved_failed_step_ids if item.retry_comparison is not None else []
            return f"Recovered workflow with {len(resolved)} resolved failed step(s)"
        if event_kind == "retry":
            unchanged = item.retry_comparison.unchanged_failed_step_ids if item.retry_comparison is not None else []
            return f"Retried workflow; {len(unchanged)} failed step(s) still unresolved"
        if event_kind == "failure":
            return f"Workflow failed with {len(item.failed_step_ids)} failed step(s)"
        if event_kind == "completed":
            return "Workflow completed successfully"
        return "Workflow ended partial without explicit failed steps"

    def _count_unresolved_failures(self, recovery_state: WorkflowRecoveryState | None) -> int:
        if recovery_state is None:
            return 0
        return len(recovery_state.unchanged_failed_step_ids) + len(recovery_state.newly_failed_step_ids)

    def _classify_health(
        self,
        latest_execution: WorkflowExecutionResult,
        recovery_state: WorkflowRecoveryState | None,
        has_recent_retry: bool,
    ) -> tuple[HealthStatus, HealthSeverity, str]:
        latest_failed_step_ids = list(latest_execution.failed_step_ids)
        if recovery_state is not None and recovery_state.recovered:
            rule = self._HEALTH_RULES[0]
            return rule["health_status"], rule["severity"], rule["last_transition"]
        if latest_execution.status == "partial" and latest_failed_step_ids:
            rule = self._HEALTH_RULES[1]
            last_transition = "failure->retry-partial" if has_recent_retry else rule["last_transition"]
            return rule["health_status"], rule["severity"], last_transition
        if latest_execution.status == "completed":
            rule = self._HEALTH_RULES[2]
            return rule["health_status"], rule["severity"], rule["last_transition"]
        rule = self._HEALTH_RULES[3]
        return rule["health_status"], rule["severity"], rule["last_transition"]

    def _iter_retry_step_ids(self, comparison) -> Iterable[str]:
        yield from comparison.previous_failed_step_ids
        yield from comparison.retried_failed_step_ids
        yield from comparison.resolved_failed_step_ids
        yield from comparison.unchanged_failed_step_ids
        yield from comparison.newly_failed_step_ids
