"""Unit tests for HotToolManager — fixed + session-hot tool exposure."""
import pytest
from app.services.hot_tool_manager import (
    HotToolManager,
    FIXED_TOOLS,
    find_dynamic_tools,
)


class TestHotToolManager:
    def test_fixed_tools_count(self):
        names = [t["name"] for t in FIXED_TOOLS]
        for name in [
            "exec_shell", "read_file", "write_file", "edit_file",
            "list_files", "search_files", "find_tool",
            "call_asset_method",
        ]:
            assert name in names
        for retired in ["list_assets", "query_asset_info", "query_asset_detail"]:
            assert retired not in names

    def test_fixed_tools_are_discoverable(self):
        found = find_dynamic_tools("asset")
        names = {tool["name"] for tool in found}
        assert "call_asset_method" in names
        assert "list_assets" not in names
        assert "query_asset_info" not in names
        assert "query_asset_detail" not in names

    def test_session_hot_only_adds_registered_non_fixed_tools(self):
        manager = HotToolManager()
        manager.register_tool({
            "name": "package_list_installed",
            "description": "List installed packages",
            "parameters": {"type": "object", "properties": {}, "required": []},
        })

        manager.discover_and_add("s1", "package")
        tools = manager.get_tools_for_session("s1")
        names = [t["name"] for t in tools]

        assert "package_list_installed" in names
        fixed_count, session_hot = manager.get_hot_counts("s1")
        assert fixed_count == len(FIXED_TOOLS)
        assert session_hot == 1

    def test_unknown_tool_not_added_to_session_hot(self):
        manager = HotToolManager()
        manager.mark_used("s1", "unknown_tool")
        _, session_hot = manager.get_hot_counts("s1")
        assert session_hot == 0

    def test_clear_session_preserves_fixed_tools(self):
        manager = HotToolManager()
        manager.register_tool({
            "name": "tool_alpha",
            "description": "Alpha tool",
            "parameters": {"type": "object", "properties": {}, "required": []},
        })
        manager.discover_and_add("s1", "alpha")

        manager.clear_session("s1")

        fixed_count, session_hot = manager.get_hot_counts("s1")
        assert fixed_count == len(FIXED_TOOLS)
        assert session_hot == 0

    def test_different_sessions_independent(self):
        manager = HotToolManager()
        manager.register_tool({
            "name": "tool1",
            "description": "1",
            "parameters": {"type": "object", "properties": {}, "required": []},
        })
        manager.register_tool({
            "name": "tool2",
            "description": "2",
            "parameters": {"type": "object", "properties": {}, "required": []},
        })

        manager.discover_and_add("s1", "tool1")
        manager.discover_and_add("s2", "tool2")

        _, s1_hot = manager.get_hot_counts("s1")
        _, s2_hot = manager.get_hot_counts("s2")

        assert s1_hot == 1
        assert s2_hot == 1
