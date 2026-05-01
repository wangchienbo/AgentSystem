from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.system.asset_center.models import InteractionDecisionEnvelope
from app.system.interaction_runtime.context_assembly import InteractionContextSnapshot


class InteractionDecisionProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class DecisionProtocolResult:
    envelope: InteractionDecisionEnvelope
    resolved_action: str


class DecisionProtocol:
    def normalize(self, envelope: InteractionDecisionEnvelope) -> DecisionProtocolResult:
        envelope.validate()
        if envelope.decision == "text":
            return DecisionProtocolResult(envelope=envelope, resolved_action="reply_text")
        if envelope.decision == "need_asset_detail_id":
            return DecisionProtocolResult(envelope=envelope, resolved_action="load_detail")
        if envelope.decision == "invoke":
            return DecisionProtocolResult(envelope=envelope, resolved_action="invoke_method")
        raise InteractionDecisionProtocolError(f"Unsupported decision: {envelope.decision}")

    def resolve_against_context(
        self,
        envelope: InteractionDecisionEnvelope,
        context: InteractionContextSnapshot,
    ) -> DecisionProtocolResult:
        result = self.normalize(envelope)
        if envelope.decision == "need_asset_detail_id":
            asset_id = envelope.need_asset_detail_id or ""
            if context.has_detail(asset_id):
                return DecisionProtocolResult(
                    envelope=InteractionDecisionEnvelope(
                        decision="text",
                        text=f"detail already loaded: {asset_id}",
                        metadata={"detail_cache_hit": True, "asset_id": asset_id},
                    ),
                    resolved_action="reply_text",
                )
        if envelope.decision == "invoke":
            invoke = envelope.invoke or {}
            if not invoke.get("asset_id") or not invoke.get("method"):
                raise InteractionDecisionProtocolError("invoke payload requires asset_id and method")
        return result
