from __future__ import annotations

from typing import Iterable

from app.models.workflow_execution import WorkflowExecutionResult
from app.models.workflow_observability import (
    WorkflowDiagnosticsSummary,
    WorkflowHealthSummary,
    WorkflowOverview,
    WorkflowRecoveryState,
    WorkflowRecoverySummary,
)


class WorkflowObservabilityService:
    def __init__(self, workflow_executor) -> None:
        self._workflow_executor = workflow_executor

    def filter_history(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
    ) -> list[WorkflowExecutionResult]:
        history = self._workflow_executor.list_history(app_instance_id)
        if workflow_id is not None:
            history = [item for item in history if item.workflow_id == workflow_id]
        if failed_step_id is not None:
            history = [item for item in history if self._matches_failed_step(item, failed_step_id)]
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
        latest_failure = diagnostics.latest_failure
        latest_retry = diagnostics.latest_retry
        recovery_state = diagnostics.recovery_state

        if latest_execution is None:
            return WorkflowHealthSummary()

        unresolved_failure_count = 0 if recovery_state is None else len(recovery_state.unchanged_failed_step_ids) + len(recovery_state.newly_failed_step_ids)
        latest_failed_step_ids = [] if latest_execution is None else list(latest_execution.failed_step_ids)
        has_recent_retry = latest_retry is not None

        if recovery_state is not None and recovery_state.recovered:
            health_status = "recovering"
            severity = "warning"
            last_transition = "failure->recovered"
        elif latest_execution.status == "partial" and latest_failed_step_ids:
            health_status = "failing"
            severity = "critical"
            last_transition = "failure" if latest_retry is None else "failure->retry-partial"
        elif latest_execution.status == "completed":
            health_status = "healthy"
            severity = "info"
            last_transition = "completed"
        else:
            health_status = "unknown"
            severity = "warning" if latest_failure is not None else "info"
            last_transition = "partial-without-failed-steps"

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

    def _matches_failed_step(self, item: WorkflowExecutionResult, failed_step_id: str) -> bool:
        if failed_step_id in item.failed_step_ids:
            return True
        comparison = item.retry_comparison
        if comparison is None:
            return False
        return failed_step_id in self._iter_retry_step_ids(comparison)

    def _iter_retry_step_ids(self, comparison) -> Iterable[str]:
        yield from comparison.previous_failed_step_ids
        yield from comparison.retried_failed_step_ids
        yield from comparison.resolved_failed_step_ids
        yield from comparison.unchanged_failed_step_ids
        yield from comparison.newly_failed_step_ids
