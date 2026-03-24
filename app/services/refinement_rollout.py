from __future__ import annotations

from app.models.proposal_review import ProposalReviewRequest
from app.models.refinement_loop import RolloutQueueItem
from app.services.proposal_review import ProposalReviewError, ProposalReviewService
from app.services.refinement_memory import RefinementMemoryStore


class RefinementRolloutError(ValueError):
    pass


class RefinementRolloutService:
    def __init__(self, memory: RefinementMemoryStore, proposal_review: ProposalReviewService) -> None:
        self._memory = memory
        self._proposal_review = proposal_review

    def transition(self, queue_id: str, action: str, reviewer: str = "system", note: str = "") -> RolloutQueueItem:
        item = self._get_queue_item(queue_id)

        if action == "approve":
            if item.status != "queued":
                raise RefinementRolloutError(f"Queue item not approvable from state: {item.status}")
            item.status = "approved"
            item.note = note or "approved for rollout"
        elif action == "apply":
            if item.status not in {"queued", "approved"}:
                raise RefinementRolloutError(f"Queue item not applicable from state: {item.status}")
            self._proposal_review.review(
                ProposalReviewRequest(
                    proposal_id=item.proposal_id,
                    action="apply",
                    reviewer=reviewer,
                    note=note or "applied from rollout queue",
                )
            )
            item.status = "applied"
            item.note = note or "applied from rollout queue"
        elif action == "reject":
            if item.status not in {"queued", "approved"}:
                raise RefinementRolloutError(f"Queue item not rejectable from state: {item.status}")
            item.status = "rejected"
            item.note = note or "rejected from rollout queue"
        elif action == "rollback":
            if item.status != "applied":
                raise RefinementRolloutError(f"Queue item not rollbackable from state: {item.status}")
            item.status = "rolled_back"
            item.note = note or "rolled back"
        else:
            raise RefinementRolloutError(f"Unsupported rollout action: {action}")

        self._memory.add_queue_item(item)
        return item

    def _get_queue_item(self, queue_id: str) -> RolloutQueueItem:
        items = [item for item in self._memory.list_queue() if item.queue_id == queue_id]
        if not items:
            raise RefinementRolloutError(f"Queue item not found: {queue_id}")
        return items[0]
