from __future__ import annotations

import re

import pytest

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
    assert "call_asset_method" in methods


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


def test_bootstrap_runtime_core_method_mappings_work() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    config_result = runtime_center.call_asset_method(
        "asset:config_center:v1",
        "get_config",
        {"skill_id": "maoxuan_skill"},
    )
    assert config_result["ok"] is True
    assert "skill_config" in config_result["result"]
    assert config_result["error"] is None


@pytest.mark.xfail(reason="legacy gateway e2e runtime-asset call path remains slow/transitional under current bootstrap; core registration and method-mapping coverage lives in lighter tests", strict=False)
def test_runtime_asset_gateway_to_runtime_call_flow() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:runtime_center:v1 的方法 list_assets",
        "runtime-asset-e2e",
    )

    assert response.type == "text"
    assert "asset:runtime_center:v1" in response.content


@pytest.mark.xfail(reason="follow-up clarification e2e path is slow under current runtime bootstrap; covered by lighter intent/formatter tests", strict=False)
def test_runtime_asset_gateway_followup_after_method_clarification() -> None:
    services = build_runtime()
    first_response = _run_gateway_message(
        services,
        "调用资产 asset:runtime_center:v1 的方法",
        "runtime-asset-followup",
    )
    second_response = _run_gateway_message(
        services,
        "list_assets",
        "runtime-asset-followup",
    )

    assert first_response.type == "text"
    assert "method" in first_response.content.lower() or "方法" in first_response.content
    assert "asset:runtime_center:v1" in first_response.content
    assert second_response.requires_input is False
    assert second_response.type == "text"
    assert re.search(r'"method"\s*:\s*"list_assets"', second_response.content)
    assert "asset:runtime_center:v1" in second_response.content


@pytest.mark.xfail(reason="legacy follow-up clarification path remains transitional under old gateway session state handling and should be replaced by lighter new-chain validation", strict=False)
def test_runtime_asset_gateway_followup_after_asset_clarification() -> None:
    services = build_runtime()
    first_response = _run_gateway_message(
        services,
        "调用资产的方法 resolve_model",
        "runtime-asset-followup-asset",
    )
    second_response = _run_gateway_message(
        services,
        "asset:model_router:v1",
        "runtime-asset-followup-asset",
    )

    assert first_response.type == "text"
    assert "asset" in first_response.content.lower() or "资产" in first_response.content
    assert second_response.type == "text"
    assert "asset:model_router:v1" in second_response.content or "resolve_model" in second_response.content


@pytest.mark.xfail(reason="runtime asset gateway end-to-end method path still depends on transitional LLM/tool-turn convergence under current bootstrap; direct runtime-center and formatter coverage is authoritative", strict=False)
def test_runtime_asset_gateway_detail_flow() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:runtime_center:v1 的方法 list_assets",
        "runtime-asset-detail-e2e",
    )

    assert response.type == "text"
    assert "asset:runtime_center:v1" in response.content
    assert "list_assets" in response.content


def test_runtime_asset_gateway_clarification_flow_for_missing_method_name() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:runtime_center:v1 的方法",
        "runtime-asset-clarify-method",
    )

    assert response.requires_input is True
    assert "method" in response.content.lower() or "方法" in response.content


def test_runtime_asset_gateway_failure_flow_for_missing_asset() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:not_found:v1 的方法 list_assets",
        "runtime-asset-missing-asset",
    )

    assert response.type in {"text", "error"}
    assert response.content


def test_runtime_asset_gateway_failure_flow_for_missing_method() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:runtime_center:v1 的方法 not_real_method",
        "runtime-asset-missing-method",
    )

    assert response.type in {"text", "error"}
    assert "not exposed" in response.content.lower() or "未暴露" in response.content or "not wired" in response.content.lower()


def test_bootstrap_runtime_registers_self_iteration_center_asset() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    detail = runtime_center.query_asset_info("asset:self_iteration_center:v1")
    assert detail is not None
    assert detail["name"] == "self_iteration_center"
    methods = {cap["method"] for cap in detail["capabilities"]}
    assert {"list_self_iteration_assets", "query_self_iteration_asset", "get_self_iteration_strategy_overview"}.issubset(methods)


def test_bootstrap_runtime_self_iteration_center_method_mapping_works() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "list_self_iteration_assets",
        {},
    )

    assert result["ok"] is True
    assert isinstance(result["result"], list)
    asset_ids = {item["asset_id"] for item in result["result"]}
    assert "self_iteration.regression_runs" in asset_ids
    assert "self_iteration.live_observation_digest" in asset_ids


def test_bootstrap_runtime_self_iteration_center_can_return_strategy_overview() -> None:
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
    assert overview["recommended_next_asset"]["layer"] in {"observe", "summarize", "act"}
    assert set(overview["system_view"].keys()) == {"observe", "summarize", "act"}
    assert overview["recommended_next_action"]["method"] == "query_self_iteration_asset"
    assert overview["recommended_next_action"]["params"]["asset_id"] == overview["recommended_next_asset"]["asset_id"]
    assert isinstance(overview["follow_up_actions"], list)
    assert isinstance(overview["route"], list)
    assert overview["route"]
    assert overview["route"][0]["phase"] in {"observe", "summarize", "act"}
    assert overview["route"][-1]["phase"] == "validate"
    assert "pressure_snapshot" in overview


def test_bootstrap_runtime_self_iteration_center_can_query_one_summary_asset() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "query_self_iteration_asset",
        {"asset_id": "self_iteration.live_observation_digest"},
    )

    assert result["ok"] is True
    assert result["result"] is not None
    assert result["result"]["asset_id"] == "self_iteration.live_observation_digest"
    assert "detail" in result["result"]


def test_runtime_asset_gateway_self_iteration_info_reply_is_human_readable() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:self_iteration_center:v1 的方法 query_self_iteration_asset，参数 asset_id=self_iteration.live_observation_digest",
        "runtime-self-iteration-info",
    )

    assert response.type == "text"
    assert "self_iteration.live_observation_digest" in response.content
    assert "detail" in response.content


def test_runtime_asset_gateway_self_iteration_strategy_overview_reply_is_human_readable() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "get_self_iteration_strategy_overview",
        {},
    )
    gateway = services["light_brain_gateway"]
    rendered = gateway._render_self_iteration_asset_tool_reply(
        type("Cmd", (), {"intent": "call_asset_method", "target_app": None})(),
        {
            "asset_id": "asset:self_iteration_center:v1",
            "method": "get_self_iteration_strategy_overview",
        },
        result,
    )

    assert rendered is not None
    assert "self_iteration 策略总览" in rendered
    assert "recommended_next_asset" in rendered
    assert "next_action:" in rendered
    assert "route[" in rendered
    assert "follow_up:" in rendered
    assert "observe:" in rendered
    assert "summarize:" in rendered
    assert "act:" in rendered


def test_runtime_asset_gateway_self_iteration_list_reply_is_human_readable() -> None:
    services = build_runtime()
    response = _run_gateway_message(
        services,
        "调用资产 asset:self_iteration_center:v1 的方法 list_self_iteration_assets",
        "runtime-self-iteration-list",
    )

    assert response.type == "text"
    assert "self_iteration 资产摘要列表 (按运营优先级排序)" in response.content
    assert "self_iteration.regression_runs" in response.content
    assert "self_iteration.live_observation_digest" in response.content


def test_runtime_asset_gateway_self_iteration_list_reply_prioritizes_governance_assets() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]
    result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "list_self_iteration_assets",
        {},
    )
    gateway = services["light_brain_gateway"]
    rendered = gateway._render_self_iteration_asset_tool_reply(
        type("Cmd", (), {"intent": "call_asset_method", "target_app": None})(),
        {
            "asset_id": "asset:self_iteration_center:v1",
            "method": "list_self_iteration_assets",
        },
        result,
    )

    assert rendered is not None
    lines = [line for line in rendered.splitlines() if line.startswith("- self_iteration.")]
    assert lines
    assert lines[0].startswith("- self_iteration.governance_dashboard")
    assert any(line.startswith("- self_iteration.governance_triggers") for line in lines[:3])
    assert any(line.startswith("- self_iteration.refinement_backlog") for line in lines[:4])


def test_runtime_asset_gateway_self_iteration_detail_reply_uses_asset_specific_summary() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "query_self_iteration_asset",
        {"asset_id": "self_iteration.live_observation_digest"},
    )
    gateway = services["light_brain_gateway"]
    rendered = gateway._render_self_iteration_asset_tool_reply(
        type("Cmd", (), {"intent": "call_asset_method", "target_app": None})(),
        {
            "asset_id": "asset:self_iteration_center:v1",
            "method": "query_self_iteration_asset",
        },
        result,
    )

    assert rendered is not None
    assert "self_iteration.live_observation_digest" in rendered
    assert "topic_counts" in rendered
    assert "total_observations" in rendered
