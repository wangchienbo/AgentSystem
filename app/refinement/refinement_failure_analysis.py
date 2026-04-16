from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.patch_proposal import PatchProposal
from app.models.refinement_loop import FailedHypothesisRecord


class FailureAwarenessResult(BaseModel):
    repeat_risk: str = Field(default="low")
    related_failed_hypothesis_ids: list[str] = Field(default_factory=list)
    novelty_note: str = ""
    gating_reason: str = ""


class RefinementFailureAnalysisService:
    def analyze(
        self,
        *,
        contradiction: str,
        proposal: PatchProposal,
        failed_hypotheses: list[FailedHypothesisRecord],
    ) -> FailureAwarenessResult:
        related: list[FailedHypothesisRecord] = []
        normalized_contradiction = contradiction.strip().lower()
        normalized_benefit = proposal.expected_benefit.strip().lower()
        normalized_target = proposal.target_type.strip().lower()

        for item in failed_hypotheses:
            contradiction_match = item.contradiction.strip().lower() == normalized_contradiction
            target_match = normalized_target in item.disproven_assumption.strip().lower() or normalized_target in item.reason.strip().lower()
            benefit_overlap = normalized_benefit and normalized_benefit in item.reason.strip().lower()
            if contradiction_match or target_match or benefit_overlap:
                related.append(item)

        if not related:
            return FailureAwarenessResult(
                repeat_risk="low",
                related_failed_hypothesis_ids=[],
                novelty_note="No closely related failed hypothesis found.",
                gating_reason="",
            )

        repeat_risk = "high" if len(related) >= 2 else "medium"
        gating_reason = (
            "Similar failed hypotheses already exist; require stronger evidence before promotion."
            if repeat_risk in {"medium", "high"}
            else ""
        )
        return FailureAwarenessResult(
            repeat_risk=repeat_risk,
            related_failed_hypothesis_ids=[item.hypothesis_id for item in related],
            novelty_note=f"Matched {len(related)} related failed hypothesis record(s).",
            gating_reason=gating_reason,
        )
