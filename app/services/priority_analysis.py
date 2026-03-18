from __future__ import annotations

from app.models.app_context import AppSharedContext
from app.models.patch_proposal import PatchProposal
from app.models.priority_analysis import PriorityAnalysisRequest, PriorityAnalysisResult, PrioritizedProposal
from app.services.app_context_store import AppContextStore, AppContextStoreError
from app.services.proposal_review import ProposalReviewService


class PriorityAnalysisError(ValueError):
    pass


class PriorityAnalysisService:
    def __init__(
        self,
        proposal_review: ProposalReviewService,
        context_store: AppContextStore | None = None,
    ) -> None:
        self._proposal_review = proposal_review
        self._context_store = context_store

    def analyze(self, request: PriorityAnalysisRequest) -> PriorityAnalysisResult:
        proposals = self._proposal_review.list_proposals(request.app_instance_id)
        if not proposals:
            raise PriorityAnalysisError(f"No proposals found for app instance: {request.app_instance_id}")

        context = self._get_context(request.app_instance_id)
        scored = [self._score_proposal(item, context) for item in proposals]
        scored.sort(key=lambda item: item[1], reverse=True)

        prioritized: list[PrioritizedProposal] = []
        for index, (proposal, score, reason, context_signals) in enumerate(scored, start=1):
            prioritized.append(
                PrioritizedProposal(
                    proposal_id=proposal.proposal_id,
                    priority_score=score,
                    rank=index,
                    reason=reason,
                    context_signals=context_signals,
                )
            )

        top = scored[0][0]
        primary_contradiction = self._describe_primary_contradiction(top, context)
        recommended_action = self._recommend_action(top, context)
        return PriorityAnalysisResult(
            app_instance_id=request.app_instance_id,
            primary_contradiction=primary_contradiction,
            prioritized=prioritized,
            recommended_action=recommended_action,
            context_summary=self._build_context_summary(context),
        )

    def _score_proposal(self, proposal: PatchProposal, context: AppSharedContext | None) -> tuple[PatchProposal, int, str, list[str]]:
        score = 0
        reasons: list[str] = []
        context_signals: list[str] = []

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

        if context is not None:
            context_sections = {entry.section for entry in context.entries}
            if "open_loops" in context_sections and proposal.target_type == "workflow":
                score += 20
                context_signals.append("open_loops")
                reasons.append("context=open_loops")
            if "constraints" in context_sections:
                score += 10
                context_signals.append("constraints")
                reasons.append("context=constraints")
            if "decisions" in context_sections and proposal.target_type in {"workflow", "runtime_policy"}:
                score += 10
                context_signals.append("decisions")
                reasons.append("context=decisions")
            if context.current_stage == "paused" and proposal.target_type == "runtime_policy":
                score -= 15
                context_signals.append("paused-stage")
                reasons.append("context=paused-stage")

        return proposal, score, ", ".join(reasons), context_signals

    def _describe_primary_contradiction(self, proposal: PatchProposal, context: AppSharedContext | None) -> str:
        if proposal.target_type == "runtime_policy":
            if context is not None and context.current_stage == "paused":
                return "当前上下文显示 app 处于暂停阶段，主要矛盾偏向恢复策略与实际占用之间的平衡，应谨慎处理 runtime continuity。"
            return "长期运行稳定性与当前运行策略之间存在主要矛盾，应优先解决 runtime continuity 问题。"
        if proposal.target_type == "workflow":
            if context is not None and any(entry.section == "open_loops" for entry in context.entries):
                return "工作流闭环能力与共享上下文中的未完成事项之间存在主要矛盾，应优先修补 open-loop handling。"
            return "工作流可靠性与当前执行链路之间存在主要矛盾，应优先修补 workflow 恢复能力。"
        return "能力复用需求与当前 skill 供给之间存在主要矛盾，应优先补齐能力层。"

    def _recommend_action(self, proposal: PatchProposal, context: AppSharedContext | None) -> str:
        if proposal.target_type == "runtime_policy" and proposal.auto_apply_allowed and proposal.risk_level == "low":
            if context is not None and context.current_stage == "paused":
                return f"优先审查 {proposal.proposal_id}，当前上下文处于 paused，建议先确认恢复策略再决定是否 apply。"
            return f"优先处理 {proposal.proposal_id}，可在校验后直接 apply。"
        return f"优先审查 {proposal.proposal_id}，确认收益与风险后再进入下一步。"

    def _get_context(self, app_instance_id: str) -> AppSharedContext | None:
        if self._context_store is None:
            return None
        try:
            return self._context_store.get_context(app_instance_id)
        except AppContextStoreError:
            return None

    def _build_context_summary(self, context: AppSharedContext | None) -> str:
        if context is None:
            return ""
        parts: list[str] = []
        if context.current_goal:
            parts.append(f"goal={context.current_goal}")
        if context.current_stage:
            parts.append(f"stage={context.current_stage}")
        sections = sorted({entry.section for entry in context.entries})
        if sections:
            parts.append("sections=" + ",".join(sections))
        return " | ".join(parts)
