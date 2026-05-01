from __future__ import annotations

from pathlib import Path

from app.system.management_presenters import (
    render_app_list,
    render_management_availability,
    render_management_status,
    render_package_detail,
    render_package_list,
    render_package_operation_result,
)
from app.system.runtime_asset_formatter import (
    append_detail_fallback,
    extract_capability_methods,
    join_kv_pairs,
    render_asset_detail_document,
    render_asset_detail_header,
    render_asset_info_summary,
    render_asset_interface_details,
    render_asset_method_catalog,
    render_asset_overview_prompt,
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
from app.system.gateway.tool_calling_interpreter import (
    SELF_ITERATION_BRANCH_GUIDANCE,
    _try_parse_self_iteration_fast_path,
    choose_turn_budget,
    is_self_iteration_like_request,
    narrow_tools_for_self_iteration_route,
)


def read_text_from_llm_responder_prompt_source() -> str:
    return Path("app/system/gateway/llm_responder.py").read_text(encoding="utf-8")


def test_light_brain_runtime_asset_intent_set_no_longer_requires_legacy_list_or_info_surface() -> None:
    content = Path("app/system/gateway/light_brain_interpreter.py").read_text(encoding="utf-8")
    assert '"call_asset_method"' in content
    assert '"call_asset_method", "query_asset_detail"' not in content
    assert '"list_assets", "query_asset_info", "call_asset_method", "query_asset_detail"' not in content


def test_self_iteration_branch_guidance_prefers_runtime_asset_first() -> None:
    assert "先参考上方已经提供的可见资产概览" in SELF_ITERATION_BRANCH_GUIDANCE
    assert "asset 不是 tool" in SELF_ITERATION_BRANCH_GUIDANCE
    assert "call_asset_method" in SELF_ITERATION_BRANCH_GUIDANCE
    assert "不要把这类问题默认降级成文件搜索" in SELF_ITERATION_BRANCH_GUIDANCE
    assert "不要把 asset 当作 tool 名称来选择" in SELF_ITERATION_BRANCH_GUIDANCE


def test_self_iteration_fast_path_maps_explicit_asset_requests() -> None:
    detail_cmd = _try_parse_self_iteration_fast_path("查看自我迭代资产详情")
    assert detail_cmd is not None
    assert detail_cmd.parameters["asset_id"] == "asset:self_iteration_center:v1"

    list_cmd = _try_parse_self_iteration_fast_path("调用资产 asset:self_iteration_center:v1 的方法 list_self_iteration_assets")
    assert list_cmd is not None
    assert list_cmd.intent == "call_asset_method"
    assert list_cmd.parameters["method"] == "list_self_iteration_assets"




def test_self_iteration_route_narrows_to_asset_tools() -> None:
    assert is_self_iteration_like_request("最近系统自我迭代情况怎么样") is True

    class DummyToolDef:
        def __init__(self, name: str):
            self.name = name
            self.description = name
            self.parameters = {"type": "object", "properties": {}, "required": []}

    defs = [
        DummyToolDef("search_files"),
        DummyToolDef("read_file"),
        DummyToolDef("list_assets"),
        DummyToolDef("query_asset_info"),
        DummyToolDef("query_asset_detail"),
        DummyToolDef("call_asset_method"),
        DummyToolDef("ask_clarification"),
        DummyToolDef("unclear"),
    ]

    narrowed = narrow_tools_for_self_iteration_route(defs)
    narrowed_names = {tool.name for tool in narrowed}

    assert narrowed_names == {"call_asset_method", "ask_clarification", "unclear"}
    assert "search_files" not in narrowed_names
    assert "read_file" not in narrowed_names


    packages = [
        {
            "asset_id": "pkg.alpha",
            "asset_type": "skill",
            "installed_version": "1.0.0",
            "version": "1.0.0",
            "installed": True,
            "description": "alpha desc",
        }
    ]

    installed_view = render_package_list(packages, header="📦 **已安装的包：**\n")
    search_view = render_package_list(packages, header="🔍 搜索结果（1 个）:\n", include_install_status=True)

    assert "pkg.alpha (skill) v1.0.0" in installed_view
    assert "alpha desc" in installed_view
    assert "[✅ 已安装]" in search_view


def test_render_management_availability_outputs_module_guard_message() -> None:
    assert render_management_availability("包管理模块") == "⚠️ 包管理模块未加载。"


    rendered = render_asset_detail_document(
        asset_id="asset:test:v1",
        asset_name="Test Asset",
        description="用于测试",
        interfaces={
            "query_asset": {
                "description": "查询资产",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            }
        },
    )

    assert "📋 **Test Asset** 详细使用说明" in rendered
    assert "资产ID: asset:test:v1" in rendered
    assert "**可用接口：**" in rendered
    assert "**query_asset** - 查询资产" in rendered


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


def test_render_asset_overview_prompt_includes_selection_guidance() -> None:
    class DummyAsset:
        def __init__(self, asset_id: str, name: str, description: str, functions: list | None = None):
            self.asset_id = asset_id
            self.name = name
            self.description = description
            self.functions = functions or []

    rendered = render_asset_overview_prompt(
        [
            DummyAsset(
                "asset:self_iteration_center:v1",
                "self_iteration_center",
                "Self-iteration governance and system-evolution navigation surface",
            )
        ],
        header="## 你可用的资产",
    )

    assert "先根据资产描述判断哪个资产最贴近当前问题" in rendered
    assert "不要因为提问里出现某些关键词就假设必须命中某个固定资产" in rendered
    assert "系统最近的演化状态、治理风险、回归观察或待优化项" in rendered
    assert "asset:self_iteration_center:v1" in rendered
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
