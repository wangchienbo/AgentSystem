from __future__ import annotations

from app.system.runtime_asset_formatter import (
    append_detail_fallback,
    extract_capability_methods,
    join_kv_pairs,
    render_asset_detail_header,
    render_asset_info_summary,
    render_asset_method_catalog,
    render_asset_summary_list,
)
from app.system.self_iteration_strategy import (
    build_asset_query_action,
    build_follow_up_actions,
    build_strategy_route,
    select_recommended_next_asset,
)
from app.system.self_iteration_strategy_formatter import (
    render_self_iteration_asset_detail,
    render_self_iteration_asset_list,
    render_self_iteration_strategy_overview,
)
from app.services.light_brain_interpreter import LightBrainInterpreter
from app.services.tool_registry import ToolRegistry, ToolDefinition, ToolParameter


def test_extract_capability_methods_respects_limit() -> None:
    methods = extract_capability_methods(
        [
            {"method": "foo"},
            {"method": "bar"},
            {"method": "baz"},
        ],
        limit=2,
    )

    assert methods == ["foo", "bar"]


def test_render_asset_info_summary_outputs_methods_and_extra_lines() -> None:
    rendered = render_asset_info_summary(
        asset_id="asset:self_iteration_center:v1",
        intro="self_iteration_center 是自我迭代资产入口。",
        capabilities=[{"method": "list_self_iteration_assets"}, {"method": "query_self_iteration_asset"}],
        extra_lines=["- 用途: 汇总并查询资产摘要"],
    )

    assert "asset:self_iteration_center:v1" in rendered
    assert "methods: list_self_iteration_assets, query_self_iteration_asset" in rendered
    assert "用途: 汇总并查询资产摘要" in rendered


def test_render_runtime_asset_summary_list_outputs_header_and_items() -> None:
    rendered = render_asset_summary_list(
        [
            {"asset_id": "asset.a", "title": "Asset A", "summary": "summary a"},
            {"asset_id": "asset.b", "title": "Asset B", "summary": "summary b"},
        ],
        header="runtime assets:",
    )

    assert "runtime assets:" in rendered
    assert "- asset.a: Asset A | summary a" in rendered
    assert "- asset.b: Asset B | summary b" in rendered


    rendered = join_kv_pairs([("alpha", 1), ("beta", 2)])

    assert rendered == "alpha=1; beta=2"


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


def test_render_self_iteration_asset_list_orders_governance_first() -> None:
    rendered = render_self_iteration_asset_list(
        [
            {
                "asset_id": "self_iteration.regression_runs",
                "title": "Regression run history",
                "summary": "5 saved runs",
                "detail": {"run_count": 5},
            },
            {
                "asset_id": "self_iteration.governance_dashboard",
                "title": "Governance dashboard",
                "summary": "2 risk flags",
                "detail": {"risk_flag_count": 2},
            },
        ]
    )

    lines = [line for line in rendered.splitlines() if line.startswith("- self_iteration.")]
    assert lines[0].startswith("- self_iteration.governance_dashboard")


def test_render_self_iteration_asset_detail_outputs_asset_specific_summary() -> None:
    rendered = render_self_iteration_asset_detail(
        {
            "asset_id": "self_iteration.live_observation_digest",
            "title": "Live chat observation digest",
            "summary": "5 observations",
            "detail": {
                "total_observations": 5,
                "topic_counts": {"hallucination": 2},
            },
        }
    )

    assert "self_iteration.live_observation_digest" in rendered
    assert "total_observations=5" in rendered
    assert "topic_counts" in rendered


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
