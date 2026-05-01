from __future__ import annotations

import pytest

from app.system.asset_center.models import InteractionDecisionEnvelope
from app.system.interaction_runtime.context_assembly import (
    InteractionContextSnapshot,
    build_initial_interaction_context,
)
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
        summaries=[{"asset_id": "asset:self_iteration_center:v1"}],
        details={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1"}
        },
    )

    result = protocol.resolve_against_context(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:self_iteration_center:v1"),
        context,
    )

    assert result.resolved_action == "reply_text"
    assert result.envelope.metadata["detail_cache_hit"] is True


def test_decision_protocol_handles_stale_detail_request_by_reloading() -> None:
    protocol = DecisionProtocol()
    context = InteractionContextSnapshot(
        summaries=[{"asset_id": "asset:self_iteration_center:v1", "registration_epoch": 3}],
        details={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1", "registration_epoch": 2}
        },
    )

    result = protocol.resolve_against_context(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:self_iteration_center:v1"),
        context,
    )

    assert result.resolved_action == "load_detail"
    assert result.envelope.metadata["detail_cache_stale"] is True
    assert result.envelope.metadata["detail_epoch"] == 2
    assert result.envelope.metadata["summary_epoch"] == 3


def test_decision_protocol_handles_missing_asset_detail_request() -> None:
    protocol = DecisionProtocol()
    context = InteractionContextSnapshot(summaries=[])

    result = protocol.resolve_against_context(
        InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:not_found:v1"),
        context,
    )

    assert result.resolved_action == "reply_text"
    assert result.envelope.metadata["missing_asset_detail"] is True


def test_initial_interaction_context_can_preload_details() -> None:
    context = build_initial_interaction_context(
        asset_summaries=[{"asset_id": "asset:self_iteration_center:v1"}],
        preload_detail_ids=["asset:self_iteration_center:v1"],
        detail_provider=lambda asset_id: {"asset_id": asset_id, "detail_level": "expanded"},
    )

    assert context.has_summary("asset:self_iteration_center:v1") is True
    assert context.has_detail("asset:self_iteration_center:v1") is True
    assert context.metadata["preloaded_detail_ids"] == ["asset:self_iteration_center:v1"]


def test_interaction_orchestrator_delegates_to_protocol() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.evaluate(
        InteractionDecisionEnvelope(decision="text", text="hello"),
        InteractionContextSnapshot(),
    )

    assert result.resolved_action == "reply_text"
    assert result.envelope.text == "hello"


def test_self_iteration_route_requests_detail_first_when_missing() -> None:
    orchestrator = InteractionOrchestrator()
    context = InteractionContextSnapshot(
        summaries=[{"asset_id": "asset:self_iteration_center:v1", "summary": "Self-iteration"}],
        details={},
    )

    result = orchestrator.evaluate_self_iteration("查看自我迭代资产详情", context)

    assert result.resolved_action == "load_detail"
    assert result.envelope.need_asset_detail_id == "asset:self_iteration_center:v1"


def test_self_iteration_route_can_invoke_list_when_context_known() -> None:
    orchestrator = InteractionOrchestrator()
    context = InteractionContextSnapshot(
        summaries=[{"asset_id": "asset:self_iteration_center:v1", "summary": "Self-iteration"}],
        details={"asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1"}},
    )

    result = orchestrator.evaluate_self_iteration("给我看看自我迭代列表", context)

    assert result.resolved_action == "invoke_method"
    assert result.envelope.invoke["method"] == "list_self_iteration_assets"


def test_config_center_route_can_invoke_simple_pilot_asset() -> None:
    orchestrator = InteractionOrchestrator()
    context = InteractionContextSnapshot(
        summaries=[{"asset_id": "asset:config_center:v1", "summary": "Config center"}],
        details={"asset:config_center:v1": {"asset_id": "asset:config_center:v1"}},
    )

    result = orchestrator.evaluate_config_center("查看 maoxuan skill 配置", context)

    assert result.resolved_action == "invoke_method"
    assert result.envelope.invoke["asset_id"] == "asset:config_center:v1"
    assert result.envelope.invoke["method"] == "get_config"


def test_interaction_orchestrator_debug_view_exposes_loaded_state() -> None:
    orchestrator = InteractionOrchestrator()
    context = InteractionContextSnapshot(
        summaries=[
            {"asset_id": "asset:config_center:v1", "registration_epoch": 2},
            {"asset_id": "asset:self_iteration_center:v1", "registration_epoch": 1},
        ],
        details={"asset:config_center:v1": {"asset_id": "asset:config_center:v1", "registration_epoch": 1}},
    )
    result = orchestrator.evaluate_config_center("查看 maoxuan skill 配置", context)
    debug_view = orchestrator.debug_view(context=context, result=result)

    assert "asset:config_center:v1" in debug_view["loaded_summaries"]
    assert "asset:config_center:v1" in debug_view["loaded_details"]
    assert debug_view["resolved_action"] == "invoke_method"
    assert debug_view["summary_epochs"]["asset:config_center:v1"] == 2
    assert debug_view["detail_epochs"]["asset:config_center:v1"] == 1
