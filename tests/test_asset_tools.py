"""Tests for app.services.asset_tools."""
import pytest

from app.models.asset import Asset, AssetFunction, AssetType, Visibility
from app.services.asset_registry import AssetRegistry
from app.services.asset_tools import (
    AssetToolExecutor,
    ToolResult,
    assemble_asset_overview_prompt,
    make_all_asset_tools,
    make_execute_path_by_key_tool,
    make_query_asset_detail_tool,
    make_solidify_workflow_tool,
)


def _make_asset(asset_id, owner_id, visibility=Visibility.PRIVATE, functions=None):
    a = Asset(
        asset_id=asset_id,
        asset_type=AssetType.APP,
        owner_id=owner_id,
        name=asset_id,
        description=f"desc for {asset_id}",
        visibility=visibility,
    )
    if functions:
        for key, name in functions:
            a.add_function(AssetFunction(
                key=key, name=name, description="",
                input_schema={"input": "string"},
                output_schema={"output": "string"},
            ))
    return a


class TestToolDefinitions:
    def test_query_asset_detail_tool(self):
        tool = make_query_asset_detail_tool()
        assert tool.name == "query_asset_detail"
        assert len(tool.parameters) == 1
        assert tool.parameters[0].name == "asset_id"

    def test_solidify_workflow_tool(self):
        tool = make_solidify_workflow_tool()
        assert tool.name == "solidify_workflow"
        assert len(tool.parameters) == 3

    def test_execute_path_by_key_tool(self):
        tool = make_execute_path_by_key_tool()
        assert tool.name == "execute_path_by_key"

    def test_all_tools(self):
        tools = make_all_asset_tools()
        assert len(tools) == 3


class TestAssemblePrompt:
    def test_empty_assets(self):
        reg = AssetRegistry()
        prompt = assemble_asset_overview_prompt(reg, "user.alice")
        assert "没有可用" in prompt

    def test_with_assets(self):
        reg = AssetRegistry()
        reg.register(_make_asset("app.novel", "user.alice", functions=[
            ("write", "写"),
            ("revise", "修改"),
        ]))
        prompt = assemble_asset_overview_prompt(reg, "user.alice")
        assert "app.novel" in prompt
        assert "写" in prompt
        assert "修改" in prompt
        assert "query_asset_detail" in prompt

    def test_only_visible_assets(self):
        reg = AssetRegistry()
        reg.register(_make_asset("app.novel", "user.alice"))
        reg.register(_make_asset("app.music", "user.bob"))
        prompt = assemble_asset_overview_prompt(reg, "user.alice")
        assert "app.novel" in prompt
        assert "app.music" not in prompt


class TestAssetToolExecutor:
    def _make_registry_and_executor(self):
        reg = AssetRegistry()
        reg.register(_make_asset("app.novel", "user.alice", functions=[
            ("write", "写"),
        ]))
        executor = AssetToolExecutor(registry=reg)
        return reg, executor

    def test_query_asset_detail_success(self):
        _, executor = self._make_registry_and_executor()
        result = executor.execute("query_asset_detail", {"asset_id": "app.novel"}, "user.alice")
        assert result.success is True
        assert result.data["asset_id"] == "app.novel"
        assert len(result.data["functions"]) == 1

    def test_query_asset_detail_not_visible(self):
        _, executor = self._make_registry_and_executor()
        result = executor.execute("query_asset_detail", {"asset_id": "app.novel"}, "user.bob")
        assert result.success is False
        assert "not found or not visible" in result.error

    def test_query_asset_detail_missing_param(self):
        _, executor = self._make_registry_and_executor()
        result = executor.execute("query_asset_detail", {}, "user.alice")
        assert result.success is False

    def test_solidify_workflow_success(self):
        reg, executor = self._make_registry_and_executor()
        # Mock orchestrator router
        def mock_router(app_id, path_key, inputs):
            return {"solidified": True, "path_key": path_key}

        executor._orchestrator_router = mock_router
        result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "write_chapter",
            "steps": [{"skill_id": "skill.writer", "action": "write"}],
        }, "user.alice")
        assert result.success is True
        assert result.data["solidified"] is True

    def test_solidify_workflow_missing_params(self):
        _, executor = self._make_registry_and_executor()
        result = executor.execute("solidify_workflow", {"app_id": "app.novel"}, "user.alice")
        assert result.success is False

    def test_solidify_workflow_app_not_visible(self):
        _, executor = self._make_registry_and_executor()
        result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "x",
            "steps": [{"skill_id": "s", "action": "a"}],
        }, "user.bob")
        assert result.success is False

    def test_solidify_workflow_no_router(self):
        _, executor = self._make_registry_and_executor()
        # No orchestrator_router set — provide valid params but no router
        result = executor.execute("solidify_workflow", {
            "app_id": "app.novel",
            "path_key": "x",
            "steps": [{"skill_id": "s", "action": "a"}],
        }, "user.alice")
        assert result.success is False
        assert "not configured" in result.error

    def test_execute_path_by_key_success(self):
        _, executor = self._make_registry_and_executor()
        def mock_router(app_id, path_key, inputs):
            return {"executed": True, "output": "chapter 1"}
        executor._orchestrator_router = mock_router
        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "write",
            "inputs": {"topic": "武侠"},
        }, "user.alice")
        assert result.success is True
        assert result.data["executed"] is True

    def test_execute_path_by_key_missing_params(self):
        _, executor = self._make_registry_and_executor()
        result = executor.execute("execute_path_by_key", {"app_id": "app.novel"}, "user.alice")
        assert result.success is False

    def test_execute_path_by_key_not_visible(self):
        _, executor = self._make_registry_and_executor()
        result = executor.execute("execute_path_by_key", {
            "app_id": "app.novel",
            "path_key": "write",
        }, "user.bob")
        assert result.success is False

    def test_unknown_tool(self):
        _, executor = self._make_registry_and_executor()
        result = executor.execute("unknown_tool", {}, "user.alice")
        assert result.success is False
        assert "Unknown" in result.error
