from app.api.operator_filters import build_refinement_filter, build_workflow_observability_filter


def test_operator_api_filter_builders_capture_shared_and_domain_specific_dimensions() -> None:
    workflow = build_workflow_observability_filter(
        app_instance_id="app.workflow",
        workflow_id="wf.demo",
        failed_step_id="step.fail",
        limit=5,
        unresolved_only=True,
        since="2026-03-24T00:00:00+00:00",
        cursor="2026-03-24T01:00:00+00:00",
    )
    refinement = build_refinement_filter(
        app_instance_id="app.refinement",
        hypothesis_id="hyp.1",
        proposal_id="proposal.1",
        status="approved",
        verification_outcome="failed",
        limit=3,
        since="2026-03-24T00:00:00+00:00",
        cursor="cursor.demo",
    )

    assert workflow.app_instance_id == "app.workflow"
    assert workflow.workflow_id == "wf.demo"
    assert workflow.failed_step_id == "step.fail"
    assert workflow.limit == 5
    assert workflow.unresolved_only is True
    assert workflow.since == "2026-03-24T00:00:00+00:00"
    assert workflow.cursor == "2026-03-24T01:00:00+00:00"

    assert refinement.app_instance_id == "app.refinement"
    assert refinement.hypothesis_id == "hyp.1"
    assert refinement.proposal_id == "proposal.1"
    assert refinement.queue_status == "approved"
    assert refinement.verification_outcome == "failed"
    assert refinement.limit == 3
    assert refinement.since == "2026-03-24T00:00:00+00:00"
    assert refinement.cursor == "cursor.demo"
