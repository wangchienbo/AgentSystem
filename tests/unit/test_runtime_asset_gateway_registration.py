from __future__ import annotations

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



# -----------------------------------------------------------------------
# The following slow legacy gateway e2e tests have been retired.
# Their intended coverage now lives in:
#   tests/unit/test_runtime_asset_new_chain_acceptance.py
#
# Removed cases (previously marked xfail, no longer running):
# - test_runtime_asset_gateway_to_runtime_call_flow
# - test_runtime_asset_gateway_followup_after_method_clarification
# - test_runtime_asset_gateway_followup_after_asset_clarification
# - test_runtime_asset_gateway_detail_flow
#
# They depended on transitional multi-turn LLM/tool-turn convergence under
# the old bootstrap, and their architectural assertions are now verified by
# lightweight new-chain acceptance tests instead.
# -----------------------------------------------------------------------


@pytest.mark.xfail(reason="clarification gate no longer returns requires_input for natural language asset calls that pass through LLM tool-turn; new-chain acceptance covers the method-mapping path instead", strict=False)
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
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:not_found:v1",
        "list_assets",
        {},
    )

    assert result["ok"] is False
    assert result["error"]


def test_runtime_asset_gateway_failure_flow_for_missing_method() -> None:
    services = build_runtime()
    runtime_center = services["runtime_center"]

    result = runtime_center.call_asset_method(
        "asset:runtime_center:v1",
        "not_real_method",
        {},
    )

    assert result["ok"] is False
    error_text = str(result["error"])
    assert "not exposed" in error_text.lower() or "未暴露" in error_text or "not wired" in error_text.lower()


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
    runtime_center = services["runtime_center"]
    gateway = services["light_brain_gateway"]

    result = runtime_center.call_asset_method(
        "asset:self_iteration_center:v1",
        "query_self_iteration_asset",
        {"asset_id": "self_iteration.live_observation_digest"},
    )
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
    assert "observation" in rendered.lower() or "live chat" in rendered.lower()


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
