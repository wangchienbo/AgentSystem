from __future__ import annotations

from app.models.patch_proposal import PatchProposal
from app.models.priority_analysis import PriorityAnalysisRequest, PriorityAnalysisResult, PrioritizedProposal
from app.services.proposal_review import ProposalReviewService


class PriorityAnalysisError(ValueError):
    pass


class PriorityAnalysisService:
    def __init__(self, proposal_review: ProposalReviewService) -> None:
        self._proposal_review = proposal_review

    def analyze(self, request: PriorityAnalysisRequest) -> PriorityAnalysisResult:
        proposals = self._proposal_review.list_proposals(request.app_instance_id)
        if not proposals:
            raise PriorityAnalysisError(f"No proposals found for app instance: {request.app_instance_id}")

        scored = [self._score_proposal(item) for item in proposals]
        scored.sort(key=lambda item: item[1], reverse=True)

        prioritized: list[PrioritizedProposal] = []
        for index, (proposal, score, reason) in enumerate(scored, start=1):
            prioritized.append(
                PrioritizedProposal(
                    proposal_id=proposal.proposal_id,
                    priority_score=score,
                    rank=index,
                    reason=reason,
                )
            )

        top = scored[0][0]
        primary_contradiction = self._describe_primary_contradiction(top)
        recommended_action = self._recommend_action(top)
        return PriorityAnalysisResult(
            app_instance_id=request.app_instance_id,
            primary_contradiction=primary_contradiction,
            prioritized=prioritized,
            recommended_action=recommended_action,
        )

    def _score_proposal(self, proposal: PatchProposal) -> tuple[PatchProposal, int, str]:
        score = 0
        reasons: list[str] = []

        if proposal.target_type == "runtime_policy":
            score += 50
            reasons.append("runtime continuity impact")
        elif proposal.target_type == "workflow":
            score += 40
            reasons.append("workflow reliability impact")
        else:
            score += 30
            reasons.append("capability impact")

        risk_bonus = {"low": 30, "medium": 15, "high": 5}[proposal.risk_level]
        score += risk_bonus
        reasons.append(f"risk={proposal.risk_level}")

        if proposal.auto_apply_allowed:
            score += 15
            reasons.append("auto-apply eligible")

        score += min(len(proposal.evidence) * 5, 20)
        reasons.append(f"evidence={len(proposal.evidence)}")

        return proposal, score, ", ".join(reasons)

    def _describe_primary_contradiction(self, proposal: PatchProposal) -> str:
        if proposal.target_type == "runtime_policy":
            return "长期运行稳定性与当前运行策略之间存在主要矛盾，应优先解决 runtime continuity 问题。"
        if proposal.target_type == "workflow":
            return "工作流可靠性与当前执行链路之间存在主要矛盾，应优先修补 workflow 恢复能力。"
        return "能力复用需求与当前 skill 供给之间存在主要矛盾，应优先补齐能力层。"

    def _recommend_action(self, proposal: PatchProposal) -> str:
        if proposal.target_type == "runtime_policy" and proposal.auto_apply_allowed and proposal.risk_level == "low":
            return f"优先处理 {proposal.proposal_id}，可在校验后直接 apply。"
        return f"优先审查 {proposal.proposal_id}，确认收益与风险后再进入下一步。"
