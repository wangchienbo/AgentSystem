from __future__ import annotations

from datetime import UTC

from app.models.workflow_execution import WorkflowExecutionResult
from app.models.workflow_observability import (
    WorkflowDashboardSummary,
    WorkflowDiagnosticsSummary,
    WorkflowHealthSummary,
    WorkflowHistoryPage,
    WorkflowObservabilityFilter,
    WorkflowOverview,
    WorkflowPageMeta,
    WorkflowRecoveryState,
    WorkflowRecoverySummary,
    WorkflowStatsSummary,
    WorkflowTimelineEvent,
    WorkflowTimelinePage,
)
from app.services.workflow_observability_helpers import (
    apply_history_filters,
    classify_health,
    count_unresolved_failures,
    iter_retry_step_ids,
)


class WorkflowObservabilityService:
    def __init__(self, workflow_executor) -> None:
        self._workflow_executor = workflow_executor

    def filter_history(self, filters: WorkflowObservabilityFilter) -> list[WorkflowExecutionResult]:
        history = self._workflow_executor.list_history(filters.app_instance_id)
        return apply_history_filters(history, filters, self._matches_failed_step, self._is_unresolved)

    def get_diagnostics_summary(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
    ) -> WorkflowDiagnosticsSummary:
        history = self.filter_history(
            WorkflowObservabilityFilter(
                app_instance_id=app_instance_id,
                workflow_id=workflow_id,
                failed_step_id=failed_step_id,
            )
        )
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
        history = self.filter_history(
            WorkflowObservabilityFilter(
                app_instance_id=app_instance_id,
                workflow_id=workflow_id,
            )
        )
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

        unresolved_failure_count = count_unresolved_failures(recovery_state)
        latest_failed_step_ids = list(latest_execution.failed_step_ids)
        has_recent_retry = latest_retry is not None
        health_status, severity, last_transition = classify_health(
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
    ) -> WorkflowHistoryPage:
        history = self.filter_history(
            WorkflowObservabilityFilter(
                app_instance_id=app_instance_id,
                workflow_id=workflow_id,
                failed_step_id=failed_step_id,
                limit=limit,
                unresolved_only=unresolved_only,
                since=since,
                cursor=cursor,
            )
        )
        next_cursor = history[-1].completed_at.isoformat() if limit is not None and len(history) == limit else None
        return WorkflowHistoryPage(
            items=history,
            meta=WorkflowPageMeta(
                returned_count=len(history),
                unresolved_count=sum(1 for item in history if self._is_unresolved(item)),
                has_more=next_cursor is not None,
                window_since=since,
                next_cursor=next_cursor,
            ),
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
        history_page = self.list_observability_history(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
            limit=limit,
            unresolved_only=unresolved_only,
            since=since,
            cursor=cursor,
        )
        items = [self._to_timeline_event(item) for item in history_page.items]
        return WorkflowTimelinePage(items=items, meta=history_page.meta)

    def get_stats_summary(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
        since: str | None = None,
    ) -> WorkflowStatsSummary:
        history = self.filter_history(
            WorkflowObservabilityFilter(
                app_instance_id=app_instance_id,
                workflow_id=workflow_id,
                failed_step_id=failed_step_id,
                since=since,
            )
        )
        latest_event_at = history[0].completed_at.isoformat() if history else None
        total_failures = sum(1 for item in history if item.status == "partial" and item.failed_step_ids)
        total_retries = sum(1 for item in history if item.retry_comparison is not None)
        total_recoveries = sum(
            1
            for item in history
            if item.retry_comparison is not None
            and item.retry_comparison.previous_status == "partial"
            and item.retry_comparison.retried_status == "completed"
        )
        total_completed = sum(1 for item in history if item.status == "completed")
        total_partial_without_failed_steps = sum(1 for item in history if item.status == "partial" and not item.failed_step_ids)
        unresolved_executions = sum(1 for item in history if self._is_unresolved(item))
        return WorkflowStatsSummary(
            total_executions=len(history),
            total_failures=total_failures,
            total_retries=total_retries,
            total_recoveries=total_recoveries,
            total_completed=total_completed,
            total_partial_without_failed_steps=total_partial_without_failed_steps,
            unresolved_executions=unresolved_executions,
            latest_event_at=latest_event_at,
        )

    def get_dashboard_summary(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
        since: str | None = None,
        timeline_limit: int = 5,
    ) -> WorkflowDashboardSummary:
        overview = self.get_overview(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
        )
        stats = self.get_stats_summary(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
            since=since,
        )
        recent_timeline = self.list_timeline_events(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
            limit=timeline_limit,
            since=since,
        )
        return WorkflowDashboardSummary(
            overview=overview,
            stats=stats,
            recent_timeline=recent_timeline,
        )

    def _matches_failed_step(self, item: WorkflowExecutionResult, failed_step_id: str) -> bool:
        if failed_step_id in item.failed_step_ids:
            return True
        comparison = item.retry_comparison
        if comparison is None:
            return False
        return failed_step_id in iter_retry_step_ids(comparison)

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

