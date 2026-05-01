from __future__ import annotations

import pytest

from app.system.asset_center.models import InteractionDecisionEnvelope
from app.system.interaction_runtime.context_assembly import InteractionContextSnapshot
from app.system.interaction_runtime.decision_protocol import (
    DecisionProtocol,
    InteractionDecisionProtocolError,
)
from app.system.interaction_runtime.interaction_orchestrator import InteractionOrchestrator


def test_decision_protocol_accepts_three_branch_envelope() -> None:
    protocol = DecisionProtocol()

    text_result = protocol.normalize(InteractionDecisionEnvelope(decision="text", text="ok"))
    detail_result = protocol.normalize(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:self_iteration_center:v1")
    )
    invoke_result = protocol.normalize(
        InteractionDecisionEnvelope(
            decision="invoke",
            invoke={"asset_id": "asset:self_iteration_center:v1", "method": "list_self_iteration_assets", "params": {}},
        )
    )

    assert text_result.resolved_action == "reply_text"
    assert detail_result.resolved_action == "load_detail"
    assert invoke_result.resolved_action == "invoke_method"


def test_decision_protocol_rejects_invalid_invoke_payload() -> None:
    protocol = DecisionProtocol()
    with pytest.raises(InteractionDecisionProtocolError):
        protocol.resolve_against_context(
            InteractionDecisionEnvelope(decision="invoke", invoke={"asset_id": "asset:self_iteration_center:v1"}),
            InteractionContextSnapshot(),
        )


def test_decision_protocol_handles_detail_cache_hit() -> None:
    protocol = DecisionProtocol()
    context = InteractionContextSnapshot(
        details={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1"}
        }
    )

    result = protocol.resolve_against_context(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:self_iteration_center:v1"),
        context,
    )

    assert result.resolved_action == "reply_text"
    assert result.envelope.metadata["detail_cache_hit"] is True


def test_interaction_orchestrator_delegates_to_protocol() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.evaluate(
        InteractionDecisionEnvelope(decision="text", text="hello"),
        InteractionContextSnapshot(),
    )

    assert result.resolved_action == "reply_text"
    assert result.envelope.text == "hello"
