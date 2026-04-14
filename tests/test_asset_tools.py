"""Tests for app.services.asset_tools."""
import pytest

from app.services.system_catalog import SystemCatalog, CatalogEntry
from app.services.asset_tools import (
    AssetToolExecutor,
    ToolResult,
    assemble_asset_overview_prompt,
    make_all_asset_tools,
    make_query_asset_detail_tool,
)


class TestToolDefinitions:
    def test_query_asset_detail_tool(self):
        tool = make_query_asset_detail_tool()
        assert tool.name == "query_asset_detail"
        assert len(tool.parameters) == 1
        assert tool.parameters[0].name == "asset_id"

    def test_all_tools(self):
        tools = make_all_asset_tools()
        assert len(tools) == 1
        assert tools[0].name == "query_asset_detail"


class TestAssemblePrompt:
    def test_empty_assets(self):
        cat = SystemCatalog(data_dir='/tmp/test_prompt_empty')
        prompt = assemble_asset_overview_prompt(cat, "user.alice")
        assert "没有可用" in prompt

    def test_with_assets(self):
        cat = SystemCatalog(data_dir='/tmp/test_prompt_with')
        cat.register(CatalogEntry(
            asset_id="app.novel",
            asset_type="app",
            owner_id="user.alice",
            name="小说创作",
            description="帮助用户创作小说",
            interfaces={
                "write": {"description": "写章节"},
                "revise": {"description": "修改"},
            },
        ))
        prompt = assemble_asset_overview_prompt(cat, "user.alice")
        assert "app.novel" in prompt
        assert "写章节" in prompt
        assert "修改" in prompt
        assert "query_asset_detail" in prompt

    def test_only_visible_assets(self):
        cat = SystemCatalog(data_dir='/tmp/test_prompt_visible')
        cat.register(CatalogEntry(
            asset_id="app.novel", asset_type="app", owner_id="user.alice",
            name="小说", description="小说创作",
        ))
        cat.register(CatalogEntry(
            asset_id="app.music", asset_type="app", owner_id="user.bob",
            name="音乐", description="音乐创作", visibility="private",
        ))
        prompt = assemble_asset_overview_prompt(cat, "user.alice")
        assert "app.novel" in prompt
        assert "app.music" not in prompt


class TestAssetToolExecutor:
    def _make_catalog_and_executor(self):
        cat = SystemCatalog(data_dir='/tmp/test_executor')
        cat.register(CatalogEntry(
            asset_id="app.novel",
            asset_type="app",
            owner_id="user.alice",
            name="小说创作",
            description="帮助用户创作小说",
            interfaces={"write": {"description": "写章节"}},
        ))
        executor = AssetToolExecutor(registry=cat)
        return cat, executor

    def test_query_asset_detail_success(self):
        _, executor = self._make_catalog_and_executor()
        result = executor.execute("query_asset_detail", {"asset_id": "app.novel"}, "user.alice")
        assert result.success is True
        assert result.data["asset_id"] == "app.novel"
        assert "write" in result.data["interfaces"]

    def test_query_asset_detail_not_visible(self):
        cat, executor = self._make_catalog_and_executor()
        # Register a private asset for bob
        cat.register(CatalogEntry(
            asset_id="app.secret", asset_type="app", owner_id="user.bob",
            name="秘密", description="秘密App", visibility="private",
        ))
        result = executor.execute("query_asset_detail", {"asset_id": "app.secret"}, "user.alice")
        assert result.success is False
        assert "not found or not visible" in result.error

    def test_query_asset_detail_missing_param(self):
        _, executor = self._make_catalog_and_executor()
        result = executor.execute("query_asset_detail", {}, "user.alice")
        assert result.success is False

    def test_unknown_tool(self):
        _, executor = self._make_catalog_and_executor()
        result = executor.execute("unknown_tool", {}, "user.alice")
        assert result.success is False
        assert "Unknown" in result.error
