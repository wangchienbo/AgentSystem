from __future__ import annotations

from app.bootstrap.runtime import build_runtime



def test_runtime_asset_new_chain_acceptance_light_brain_gateway_asset_descriptor_is_queryable() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    detail = runtime_center.query_asset_info("asset:light_brain_gateway:v1")

    assert detail is not None
    assert detail["asset_id"] == "asset:light_brain_gateway:v1"
    assert detail["name"] == "light_brain_gateway"
    assert detail["asset_kind"] == "core_runtime_asset"
    methods = {cap["method"] for cap in detail["capabilities"]}
    assert "call_asset_method" in methods



def test_runtime_asset_new_chain_acceptance_runtime_center_list_assets_is_callable_via_gateway_asset_mapping() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:light_brain_gateway:v1",
        "list_assets",
        {},
    )

    assert result["ok"] is True
    assert result["asset_id"] == "asset:light_brain_gateway:v1"
    assert result["error"] is None
    assert isinstance(result["result"], list)
    asset_ids = {item["asset_id"] for item in result["result"]}
    assert "asset:runtime_center:v1" in asset_ids
    assert "asset:config_center:v1" in asset_ids



def test_runtime_asset_new_chain_acceptance_config_center_get_config_is_callable() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:config_center:v1",
        "get_config",
        {"skill_id": "maoxuan_skill"},
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert "skill_config" in result["result"]



def test_runtime_asset_new_chain_acceptance_self_iteration_summary_assets_are_navigable() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    list_result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "list_self_iteration_assets",
        {},
    )
    assert list_result["ok"] is True
    assets = list_result["result"]
    asset_ids = {item["asset_id"] for item in assets}
    assert "self_iteration.regression_runs" in asset_ids
    assert "self_iteration.live_observation_digest" in asset_ids

    query_result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "query_self_iteration_asset",
        {"asset_id": "self_iteration.live_observation_digest"},
    )
    assert query_result["ok"] is True
    assert query_result["result"]["asset_id"] == "self_iteration.live_observation_digest"
    assert "detail" in query_result["result"]



def test_runtime_asset_new_chain_acceptance_self_iteration_strategy_surface_is_available() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "get_self_iteration_strategy_overview",
        {},
    )

    assert result["ok"] is True
    overview = result["result"]
    assert overview["recommended_next_asset"]["asset_id"]
    assert overview["recommended_next_action"]["method"] == "query_self_iteration_asset"
    assert isinstance(overview["follow_up_actions"], list)
    assert isinstance(overview["route"], list)
    assert overview["route"][-1]["phase"] == "validate"



def test_runtime_asset_new_chain_acceptance_missing_method_surfaces_structured_failure() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:runtime_center:v1",
        "not_real_method",
        {},
    )

    assert result["ok"] is False
    assert result["error"]
    assert "not exposed" in result["error"].lower() or "未暴露" in result["error"] or "not wired" in result["error"].lower()
