from __future__ import annotations

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


def _run_gateway_message(services: dict, message: str, session_id: str):
    gateway = services["light_brain_gateway"]
    response = gateway.process_message(
        ChatMessageRequest(
            user_id="system",
            channel="test",
            message=message,
            session_id=session_id,
        )
    )
    if hasattr(response, "__await__"):
        import asyncio
        response = asyncio.run(response)
    return response


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
    assert result["error"] is None
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
    assert router_result["error_type"] is None

    config_result = runtime_center.call_asset_method(
        "asset:config_center:v1",
        "get_config",
        {"skill_id": "maoxuan_skill"},
    )
    assert config_result["ok"] is True
    assert "skill_config" in config_result["result"]
    assert config_result["error"] is None


def test_runtime_asset_info_and_detail_have_distinct_levels() -> None:
    services = build_runtime()
    asset_tool_executor = services["asset_tool_executor"]

    info_result = asset_tool_executor.execute(
        "query_asset_info",
        {"asset_id": "asset:runtime_center:v1"},
        "system",
    )
    detail_result = asset_tool_executor.execute(
        "query_asset_detail",
        {"asset_id": "asset:runtime_center:v1"},
        "system",
    )

    assert info_result.success is True
    assert detail_result.success is True
    assert info_result.data["detail_level"] == "descriptor"
    assert detail_result.data["detail_level"] == "expanded"
    assert "capability_methods" in detail_result.data


def test_runtime_asset_gateway_to_runtime_call_flow() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:runtime_center:v1 的方法 list_assets",
        "runtime-asset-e2e",
    )

    assert response.type == "text"
    assert "asset:runtime_center:v1" in response.content


def test_runtime_asset_gateway_failure_flow_for_missing_asset() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "查看资产 asset:not_found:v1 的详情",
        "runtime-asset-missing-asset",
    )

    assert response.type in {"text", "error"}
    assert "not found" in response.content.lower() or "未找到" in response.content


def test_runtime_asset_gateway_failure_flow_for_missing_method() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:runtime_center:v1 的方法 not_real_method",
        "runtime-asset-missing-method",
    )

    assert response.type in {"text", "error"}
    assert "not exposed" in response.content.lower() or "未暴露" in response.content or "not wired" in response.content.lower()
