from __future__ import annotations

from app.bootstrap.runtime import build_runtime


def test_self_iteration_new_chain_runs_through_runtime_services() -> None:
    services = build_runtime()
    orchestrator = services["interaction_orchestrator"]
    context = services["interaction_context_snapshot"]
    invoke_asset_envelope = services["invoke_asset_envelope"]

    result = orchestrator.evaluate_self_iteration("给我看看自我迭代列表", context)
    execution = invoke_asset_envelope(result.envelope)

    assert result.resolved_action == "invoke_method"
    assert execution["ok"] is True
    assert execution["resolved_call"]["asset_id"] == "asset:self_iteration_center:v1"
    assert execution["resolved_call"]["method"] == "list_self_iteration_assets"
    assert isinstance(execution["execution"]["result"], list)


def test_config_center_new_chain_runs_through_runtime_services() -> None:
    services = build_runtime()
    orchestrator = services["interaction_orchestrator"]
    context = services["interaction_context_snapshot"]
    safe_invoke_asset = services["safe_invoke_asset"]

    result = orchestrator.evaluate_config_center("查看 maoxuan skill 配置", context)
    invoke = result.envelope.invoke or {}
    execution = safe_invoke_asset(
        asset_id=invoke["asset_id"],
        method=invoke["method"],
        params=invoke.get("params") or {},
    )

    assert result.resolved_action == "invoke_method"
    assert execution["ok"] is True
    assert execution["resolved_call"]["asset_id"] == "asset:config_center:v1"
    assert execution["resolved_call"]["method"] == "get_config"
    assert "skill_config" in execution["execution"]["result"]


def test_interaction_debug_view_matches_runtime_invoke_result() -> None:
    services = build_runtime()
    orchestrator = services["interaction_orchestrator"]
    context = services["interaction_context_snapshot"]
    debug_view = services["interaction_debug_view"]

    result = orchestrator.evaluate_config_center("查看 maoxuan skill 配置", context)
    snapshot = debug_view(result)

    assert "asset:config_center:v1" in snapshot["loaded_summaries"]
    assert snapshot["decision"]["decision"] == "invoke"
    assert snapshot["decision"]["invoke"]["asset_id"] == "asset:config_center:v1"
    assert snapshot["resolved_action"] == "invoke_method"
    assert "detail_epochs" in snapshot
    assert "summary_epochs" in snapshot
