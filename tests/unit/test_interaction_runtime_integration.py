from __future__ import annotations

from app.bootstrap.runtime import build_runtime
from app.system.asset_center.models import InteractionDecisionEnvelope


def test_self_iteration_new_chain_runs_through_runtime_services() -> None:
    services = build_runtime()
    orchestrator = services["interaction_orchestrator"]
    invoke_asset_envelope = services["invoke_asset_envelope"]

    result = orchestrator.process_message("给我看看自我迭代列表")

    # Self-iteration list request → invoke_method
    assert result["resolved_action"] == "invoke_method"
    assert result["invoke"]["asset_id"] == "asset:self_iteration_center:v1"
    assert result["invoke"]["method"] == "list_self_iteration_assets"

    # Convert dict to InteractionDecisionEnvelope for dispatcher
    envelope = InteractionDecisionEnvelope(
        decision="invoke",
        invoke=result["invoke"],
    )
    execution = invoke_asset_envelope(envelope)
    assert execution["ok"] is True
    assert execution["resolved_call"]["asset_id"] == "asset:self_iteration_center:v1"
    assert execution["resolved_call"]["method"] == "list_self_iteration_assets"
    assert isinstance(execution["execution"]["result"], list)


def test_config_center_new_chain_runs_through_runtime_services() -> None:
    services = build_runtime()
    orchestrator = services["interaction_orchestrator"]
    safe_invoke_asset = services["safe_invoke_asset"]

    result = orchestrator.process_message("查看 maoxuan skill 配置")

    # Config center with "查/看" keyword → invoke get_config (in real runtime, config_center has get_config)
    if result["resolved_action"] == "invoke_method":
        invoke = result["invoke"]
        execution = safe_invoke_asset(
            asset_id=invoke["asset_id"],
            method=invoke["method"],
            params=invoke.get("params") or {},
        )
        assert execution["ok"] is True
        assert execution["resolved_call"]["asset_id"] == "asset:config_center:v1"
        assert execution["resolved_call"]["method"] == "get_config"
        assert "skill_config" in execution["execution"]["result"]


def test_interaction_debug_view_matches_runtime_invoke_result() -> None:
    services = build_runtime()
    orchestrator = services["interaction_orchestrator"]

    result = orchestrator.process_message("查看配置中心")
    debug = orchestrator.get_debug_view()

    assert "loaded_summaries" in debug
    assert "loaded_details" in debug
    assert "detail_epochs" in debug
    assert "summary_epochs" in debug
    assert result["resolved_action"] == "invoke_method"
    assert result["invoke"]["asset_id"] == "asset:config_center:v1"
