from __future__ import annotations

from app.bootstrap.runtime import build_runtime


def test_bootstrap_runtime_registers_light_brain_gateway_asset() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    detail = runtime_center.query_asset_info("asset:light_brain_gateway:v1")
    assert detail is not None
    assert detail["name"] == "light_brain_gateway"
    assert detail["asset_kind"] == "core_runtime_asset"

    methods = {cap["method"] for cap in detail["capabilities"]}
    assert {"list_assets", "query_asset_info", "call_asset_method"}.issubset(methods)


def test_bootstrap_runtime_gateway_asset_method_mapping_works() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:light_brain_gateway:v1",
        "list_assets",
        {},
    )

    assert result["ok"] is True
    assert result["asset_id"] == "asset:light_brain_gateway:v1"
    assert isinstance(result["result"], list)
    asset_ids = {item["asset_id"] for item in result["result"]}
    assert "asset:light_brain_gateway:v1" in asset_ids
    assert "asset:runtime_center:v1" in asset_ids


def test_bootstrap_runtime_core_method_mappings_work() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    router_result = runtime_center.call_asset_method(
        "asset:model_router:v1",
        "resolve_model",
        {"caller": "skill:test_skill"},
    )
    assert router_result["ok"] is True
    assert router_result["result"]["model_name"]

    config_result = runtime_center.call_asset_method(
        "asset:config_center:v1",
        "get_config",
        {"skill_id": "maoxuan_skill"},
    )
    assert config_result["ok"] is True
    assert "skill_config" in config_result["result"]
