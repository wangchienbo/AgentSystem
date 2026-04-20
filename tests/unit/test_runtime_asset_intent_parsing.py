from __future__ import annotations

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
