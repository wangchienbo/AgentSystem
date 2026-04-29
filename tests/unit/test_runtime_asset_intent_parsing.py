from __future__ import annotations

from app.system.self_iteration_strategy import (
    build_asset_query_action,
    build_follow_up_actions,
    build_strategy_route,
    select_recommended_next_asset,
)


def test_select_recommended_next_asset_prefers_risk_flags() -> None:
    recommendation = select_recommended_next_asset(
        pressure_snapshot={
            "risk_flag_count": 2,
            "trigger_count": 1,
            "queue_count": 3,
            "failed_hypothesis_count": 1,
            "total_observations": 4,
            "run_count": 5,
        }
    )

    assert recommendation["asset_id"] == "self_iteration.governance_dashboard"
    assert recommendation["layer"] == "summarize"


def test_build_follow_up_actions_excludes_recommended_asset() -> None:
    actions = build_follow_up_actions(recommended_asset_id="self_iteration.governance_dashboard")

    assert actions
    assert all(action["params"]["asset_id"] != "self_iteration.governance_dashboard" for action in actions)


def test_build_strategy_route_ends_with_validate() -> None:
    recommended = {
        "asset_id": "self_iteration.governance_triggers",
        "layer": "act",
        "reason": "trigger pressure",
    }
    next_action = build_asset_query_action("self_iteration.governance_triggers", reason="trigger pressure")

    route = build_strategy_route(
        recommended_next_asset=recommended,
        recommended_next_action=next_action,
    )

    assert route[0]["phase"] == "act"
    assert route[-1]["phase"] == "validate"
    assert route[-1]["asset_id"] == "self_iteration.live_observation_digest"

from app.services.light_brain_interpreter import LightBrainInterpreter
from app.services.tool_registry import ToolRegistry, ToolDefinition, ToolParameter


class TestRuntimeAssetIntentParsing:
    def setup_method(self):
        self.interpreter = LightBrainInterpreter()
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="list_assets",
            description="列出运行态资产",
            parameters=[ToolParameter("filter", "string", "过滤词", required=False)],
            category="asset",
        ))
        registry.register(ToolDefinition(
            name="query_asset_info",
            description="查询运行态资产信息",
            parameters=[ToolParameter("asset_id", "string", "资产ID", required=True)],
            category="asset",
        ))
        registry.register(ToolDefinition(
            name="call_asset_method",
            description="调用运行态资产方法",
            parameters=[
                ToolParameter("asset_id", "string", "资产ID", required=True),
                ToolParameter("method", "string", "方法", required=True),
            ],
            category="asset",
        ))
        registry.register(ToolDefinition(
            name="query_asset_detail",
            description="查询运行态资产详细说明",
            parameters=[ToolParameter("asset_id", "string", "资产ID", required=True)],
            category="asset",
        ))
        self.interpreter.set_tool_registry(registry)

    def test_tool_aware_list_assets_intent(self):
        cmd = self.interpreter.interpret("看看现在有哪些运行态资产")
        assert cmd.intent == "list_assets"
        assert cmd.confidence >= 0.8
        assert not cmd.requires_clarification

    def test_tool_aware_query_asset_info_extracts_asset_id(self):
        cmd = self.interpreter.interpret("查看资产 asset:runtime_center:v1 的详情")
        assert cmd.intent == "query_asset_info"
        assert cmd.parameters.get("asset_id") == "asset:runtime_center:v1"
        assert not cmd.requires_clarification

    def test_tool_aware_call_asset_method_extracts_target(self):
        cmd = self.interpreter.interpret("调用资产 asset:model_router:v1 的方法 resolve_model")
        assert cmd.intent == "call_asset_method"
        assert cmd.parameters.get("asset_id") == "asset:model_router:v1"
        assert cmd.parameters.get("method") == "resolve_model"
        assert not cmd.requires_clarification

    def test_tool_aware_call_asset_method_needs_clarification_when_missing_parts(self):
        cmd = self.interpreter.interpret("调用资产方法")
        assert cmd.intent == "call_asset_method"
        assert cmd.requires_clarification

    def test_tool_aware_call_asset_method_needs_method_name_when_asset_known(self):
        cmd = self.interpreter.interpret("调用资产 asset:runtime_center:v1 的方法")
        assert cmd.intent == "call_asset_method"
        assert cmd.parameters.get("asset_id") == "asset:runtime_center:v1"
        assert cmd.requires_clarification
        assert "method" in (cmd.clarification_question or "").lower() or "方法" in (cmd.clarification_question or "")

    def test_tool_aware_call_asset_method_needs_asset_id_when_method_known(self):
        cmd = self.interpreter.interpret("调用资产的方法 resolve_model")
        assert cmd.intent == "call_asset_method"
        assert cmd.parameters.get("method") == "resolve_model"
        assert cmd.requires_clarification
        assert "asset_id" in (cmd.clarification_question or "").lower() or "资产" in (cmd.clarification_question or "")

    def test_self_iteration_alias_maps_to_runtime_asset_info(self):
        cmd = self.interpreter.interpret("查看自我迭代资产详情")
        assert cmd.intent == "query_asset_info"
        assert cmd.parameters.get("asset_id") == "asset:self_iteration_center:v1"
        assert not cmd.requires_clarification

    def test_governance_asset_alias_maps_to_runtime_asset_detail(self):
        cmd = self.interpreter.interpret("看看治理资产怎么用")
        assert cmd.intent == "query_asset_detail"
        assert cmd.parameters.get("asset_id") == "asset:self_iteration_center:v1"
        assert not cmd.requires_clarification
