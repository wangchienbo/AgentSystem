from app.api.refinement_observability import build_refinement_filter


def test_build_refinement_filter_captures_supported_query_dimensions() -> None:
    filters = build_refinement_filter(
        app_instance_id="app.demo",
        hypothesis_id="hyp.1",
        proposal_id="proposal.1",
        status="approved",
        verification_outcome="failed",
        limit=3,
    )

    assert filters.app_instance_id == "app.demo"
    assert filters.hypothesis_id == "hyp.1"
    assert filters.proposal_id == "proposal.1"
    assert filters.queue_status == "approved"
    assert filters.verification_outcome == "failed"
    assert filters.limit == 3
