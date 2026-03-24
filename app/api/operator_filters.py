from __future__ import annotations

from app.models.refinement_loop import RefinementFilter
from app.models.workflow_observability import WorkflowObservabilityFilter


def build_workflow_observability_filter(
    app_instance_id: str,
    workflow_id: str | None = None,
    failed_step_id: str | None = None,
    limit: int | None = None,
    unresolved_only: bool = False,
    since: str | None = None,
    cursor: str | None = None,
) -> WorkflowObservabilityFilter:
    return WorkflowObservabilityFilter(
        app_instance_id=app_instance_id,
        workflow_id=workflow_id,
        failed_step_id=failed_step_id,
        limit=limit,
        unresolved_only=unresolved_only,
        since=since,
        cursor=cursor,
    )


def build_refinement_filter(
    app_instance_id: str | None = None,
    hypothesis_id: str | None = None,
    proposal_id: str | None = None,
    status: str | None = None,
    verification_outcome: str | None = None,
    limit: int | None = None,
    since: str | None = None,
    cursor: str | None = None,
) -> RefinementFilter:
    return RefinementFilter(
        app_instance_id=app_instance_id,
        hypothesis_id=hypothesis_id,
        proposal_id=proposal_id,
        queue_status=status,
        verification_outcome=verification_outcome,
        limit=limit,
        since=since,
        cursor=cursor,
    )
