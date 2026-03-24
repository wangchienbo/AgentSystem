from app.models.operator_filters import OperatorFilterParams
from app.models.refinement_loop import RefinementFilter
from app.models.workflow_observability import WorkflowObservabilityFilter


def test_operator_filter_params_shared_defaults() -> None:
    params = OperatorFilterParams()
    assert params.app_instance_id is None
    assert params.limit is None
    assert params.since is None
    assert params.cursor is None


def test_workflow_and_refinement_filters_extend_shared_operator_params() -> None:
    workflow = WorkflowObservabilityFilter(
        app_instance_id="app.workflow",
        workflow_id="wf.demo",
        failed_step_id="step.fail",
        limit=5,
        unresolved_only=True,
        since="2026-03-24T00:00:00+00:00",
        cursor="2026-03-24T01:00:00+00:00",
    )
    refinement = RefinementFilter(
        app_instance_id="app.refinement",
        hypothesis_id="hyp.1",
        proposal_id="proposal.1",
        queue_status="approved",
        verification_outcome="failed",
        limit=3,
        since="2026-03-24T00:00:00+00:00",
        cursor="cursor.demo",
    )

    assert workflow.app_instance_id == "app.workflow"
    assert workflow.limit == 5
    assert workflow.since == "2026-03-24T00:00:00+00:00"
    assert workflow.cursor == "2026-03-24T01:00:00+00:00"
    assert workflow.unresolved_only is True

    assert refinement.app_instance_id == "app.refinement"
    assert refinement.limit == 3
    assert refinement.since == "2026-03-24T00:00:00+00:00"
    assert refinement.cursor == "cursor.demo"
    assert refinement.queue_status == "approved"
    assert refinement.verification_outcome == "failed"
