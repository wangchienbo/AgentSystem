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
