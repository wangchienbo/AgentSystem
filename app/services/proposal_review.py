from __future__ import annotations

from app.models.patch_proposal import PatchProposal, SelfRefinementResult
from app.models.proposal_review import ProposalReviewRecord, ProposalReviewRequest
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_state_store import RuntimeStateStore


class ProposalReviewError(ValueError):
    pass


class ProposalReviewService:
    def __init__(self, lifecycle: AppLifecycleService, store: RuntimeStateStore | None = None) -> None:
        self._lifecycle = lifecycle
        self._proposals: dict[str, PatchProposal] = {}
        self._reviews: dict[str, ProposalReviewRecord] = {}
        self._store = store

    def register_proposals(self, result: SelfRefinementResult) -> list[PatchProposal]:
        for proposal in result.proposals:
            self._proposals[proposal.proposal_id] = proposal
            self._reviews.setdefault(proposal.proposal_id, ProposalReviewRecord(proposal_id=proposal.proposal_id))
        self._persist()
        return result.proposals

    def list_proposals(self, app_instance_id: str | None = None) -> list[PatchProposal]:
        proposals = list(self._proposals.values())
        if app_instance_id is None:
            return proposals
        return [item for item in proposals if item.app_instance_id == app_instance_id]

    def list_reviews(self) -> list[ProposalReviewRecord]:
        return list(self._reviews.values())

    def review(self, request: ProposalReviewRequest) -> ProposalReviewRecord:
        proposal = self._get_proposal(request.proposal_id)
        review = self._reviews.setdefault(request.proposal_id, ProposalReviewRecord(proposal_id=request.proposal_id))

        if request.action == "approve":
            review.status = "approved"
        elif request.action == "reject":
            review.status = "rejected"
        elif request.action == "apply":
            self._apply_proposal(proposal, review)
        else:
            raise ProposalReviewError(f"Unsupported review action: {request.action}")

        review.reviewer = request.reviewer
        review.note = request.note
        self._persist()
        return review

    def _apply_proposal(self, proposal: PatchProposal, review: ProposalReviewRecord) -> None:
        instance = self._lifecycle.get_instance(proposal.app_instance_id)
        if proposal.target_type == "runtime_policy":
            if proposal.risk_level != "low" or not proposal.auto_apply_allowed:
                raise ProposalReviewError(f"Proposal not eligible for auto-apply: {proposal.proposal_id}")
            idle_strategy = proposal.patch.get("idle_strategy")
            if idle_strategy:
                instance.runtime_policy.idle_strategy = idle_strategy
                review.status = "applied"
                return
            raise ProposalReviewError(f"Unsupported runtime policy patch: {proposal.proposal_id}")
        raise ProposalReviewError(f"Apply not supported for target type: {proposal.target_type}")

    def _get_proposal(self, proposal_id: str) -> PatchProposal:
        if proposal_id not in self._proposals:
            raise ProposalReviewError(f"Proposal not found: {proposal_id}")
        return self._proposals[proposal_id]

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("patch_proposals", self._proposals)
        self._store.save_mapping("proposal_reviews", self._reviews)
