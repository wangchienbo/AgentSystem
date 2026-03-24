from __future__ import annotations

from app.models.refinement_loop import RefinementFilter


def build_refinement_filter(
    app_instance_id: str | None = None,
    hypothesis_id: str | None = None,
    proposal_id: str | None = None,
    status: str | None = None,
    verification_outcome: str | None = None,
    limit: int | None = None,
) -> RefinementFilter:
    return RefinementFilter(
        app_instance_id=app_instance_id,
        hypothesis_id=hypothesis_id,
        proposal_id=proposal_id,
        queue_status=status,
        verification_outcome=verification_outcome,
        limit=limit,
    )
