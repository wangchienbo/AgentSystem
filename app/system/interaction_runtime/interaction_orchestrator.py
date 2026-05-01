from __future__ import annotations

from app.system.asset_center.models import InteractionDecisionEnvelope
from app.system.interaction_runtime.context_assembly import InteractionContextSnapshot
from app.system.interaction_runtime.decision_protocol import DecisionProtocol, DecisionProtocolResult


class InteractionOrchestrator:
    def __init__(self, protocol: DecisionProtocol | None = None) -> None:
        self._protocol = protocol or DecisionProtocol()

    def evaluate(
        self,
        envelope: InteractionDecisionEnvelope,
        context: InteractionContextSnapshot,
    ) -> DecisionProtocolResult:
        return self._protocol.resolve_against_context(envelope, context)

    def evaluate_self_iteration(
        self,
        user_message: str,
        context: InteractionContextSnapshot,
    ) -> DecisionProtocolResult:
        return self._protocol.propose_for_self_iteration(
            user_message=user_message,
            context=context,
        )

    def evaluate_config_center(
        self,
        user_message: str,
        context: InteractionContextSnapshot,
    ) -> DecisionProtocolResult:
        return self._protocol.propose_for_config_center(
            user_message=user_message,
            context=context,
        )

    def debug_view(
        self,
        *,
        context: InteractionContextSnapshot,
        result: DecisionProtocolResult,
    ) -> dict[str, object]:
        return {
            "loaded_summaries": context.list_summary_asset_ids(),
            "loaded_details": sorted(context.details.keys()),
            "decision": result.envelope.to_dict(),
            "resolved_action": result.resolved_action,
        }
