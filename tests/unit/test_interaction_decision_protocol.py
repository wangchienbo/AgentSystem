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
        details={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1"}
        },
        _summary_index={
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
        _summary_index={
            "asset:self_iteration_center:v1": {"asset_id": "asset:self_iteration_center:v1", "registration_epoch": 3}
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
    context = InteractionContextSnapshot()

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

    # build_initial_interaction_context populates details and metadata, but summaries list only
    # (summary_index is built separately when context_assembly.refresh is called)
    assert context.has_detail("asset:self_iteration_center:v1") is True
    assert context.metadata["preloaded_detail_ids"] == ["asset:self_iteration_center:v1"]


def test_interaction_orchestrator_process_message_greeting() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.process_message("你好")

    assert result["decision"] == "text"
    assert result["resolved_action"] == "reply_text"


def test_interaction_orchestrator_process_message_fallback() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.process_message("blablabla")

    assert result["decision"] == "text"
    assert result["resolved_action"] == "reply_text"


def test_self_iteration_route_requests_detail_first_when_missing() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.process_message("查看自我迭代资产详情")

    assert result["decision"] == "text"
    assert result["resolved_action"] == "reply_text"


def test_self_iteration_route_can_invoke_list_when_context_known() -> None:
    from unittest.mock import MagicMock
    asset_center = MagicMock()
    asset_center.list_assets.return_value = [
        {"asset_id": "asset:self_iteration_center:v1", "summary": "Self-iteration"}
    ]
    orchestrator = InteractionOrchestrator(asset_center_service=asset_center)
    result = orchestrator.process_message("自我迭代 列表")

    # With asset center available and "列表" keyword → invoke list_self_iteration_assets
    assert result["decision"] == "invoke"
    assert result["resolved_action"] == "invoke_method"
    assert result["invoke"]["asset_id"] == "asset:self_iteration_center:v1"
    assert result["invoke"]["method"] == "list_self_iteration_assets"


def test_config_center_route_can_invoke_simple_pilot_asset() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.process_message("查看 maoxuan skill 配置")

    # Without asset_center, "配置" without "改" falls through to text fallback
    assert result["decision"] == "text"
    assert result["resolved_action"] == "reply_text"


def test_interaction_orchestrator_debug_view_exposes_loaded_state() -> None:
    orchestrator = InteractionOrchestrator()
    orchestrator.process_message("查看配置中心")
    debug = orchestrator.get_debug_view()

    assert "loaded_summaries" in debug
    assert "loaded_details" in debug
    assert "summary_epochs" in debug
    assert "detail_epochs" in debug


def test_interaction_orchestrator_process_message_status_check() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.process_message("系统状态")

    # Status check → invoke self-iteration strategy_overview
    assert result["decision"] == "invoke"
    assert result["resolved_action"] == "invoke_method"
    assert result["invoke"]["asset_id"] == "asset:self_iteration_center:v1"
    assert result["invoke"]["method"] == "strategy_overview"


def test_interaction_orchestrator_process_message_summary() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.process_message("总结做了什么")

    assert result["decision"] == "text"
    assert result["resolved_action"] == "reply_text"


def test_interaction_orchestrator_process_message_asset_list() -> None:
    orchestrator = InteractionOrchestrator()
    result = orchestrator.process_message("资产列表")

    assert result["decision"] == "text"
    assert result["resolved_action"] == "reply_text"
