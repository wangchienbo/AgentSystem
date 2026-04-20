"""Unit tests for HotToolManager — three-layer tool set."""
import pytest
from app.services.hot_tool_manager import (
    HotToolManager,
    FIXED_TOOLS,
    FIXED_TOOL_NAMES,
    find_dynamic_tools,
)


class TestHotToolManager:
    """HotToolManager: Fixed + Global Hot + Session Hot layers."""

    def test_fixed_tools_count(self):
        """Fixed set: 7 core + 1 system = 8 total."""
        assert len(FIXED_TOOLS) == 8
        names = [t["name"] for t in FIXED_TOOLS]
        for name in ["exec_shell", "read_file", "write_file", "edit_file",
                     "list_files", "search_files", "find_tool"]:
            assert name in names
        assert "call_asset_method" in names

    def test_warm_from_static_asset(self):
        """Global hot tools are warmed from static assets at startup."""
        manager = HotToolManager()
        
        # Simulate startup warmup from RuntimeCenter
        manager.warm_from_static_asset(
            asset_id="asset:app_management:v1",
            capabilities=[
                {"method": "start_app", "description": "Start an app"},
                {"method": "stop_app", "description": "Stop an app"},
                {"method": "_internal_method", "description": "Skip this"},
            ],
        )
        
        global_hot, session_hot = manager.get_hot_counts("any-session")
        # _internal_method should be skipped
        assert global_hot == 2
        
        # Tool should be discoverable
        found = find_dynamic_tools("start")
        assert any("start_app" in f.get("name", "") for f in found)

    def test_tools_include_warmed_hot(self):
        """Warmed tools are included in session tools."""
        manager = HotToolManager()
        manager.warm_from_static_asset(
            "asset:runtime_center:v1",
            [{"method": "list_assets", "description": "List assets"}],
        )
        
        tools = manager.get_tools_for_session("s1")
        names = [t["name"] for t in tools]
        assert "asset:runtime_center:v1:list_assets" in names

    def test_session_hot_accumulates(self):
        """Session hot tools accumulate as tools are used/discovered."""
        manager = HotToolManager()
        manager.warm_from_static_asset(
            "asset:test:v1",
            [{"method": "method_a", "description": "A"}, {"method": "method_b", "description": "B"}],
        )
        
        # Simulate discovery
        manager.discover_and_add("s1", "method")
        global_hot, session_hot = manager.get_hot_counts("s1")
        assert session_hot == 2

    def test_clear_session_preserves_global_hot(self):
        """Clearing session preserves global hot tools."""
        manager = HotToolManager()
        manager.warm_from_static_asset(
            "asset:test:v1",
            [{"method": "always_available", "description": "Always"}],
        )
        manager.discover_and_add("s1", "always")
        
        manager.clear_session("s1")
        
        global_hot, session_hot = manager.get_hot_counts("s1")
        assert global_hot == 1
        assert session_hot == 0

    def test_different_sessions_independent(self):
        """Different sessions have independent session hot sets."""
        manager = HotToolManager()
        manager.warm_from_static_asset(
            "asset:test:v1",
            [{"method": "tool1", "description": "1"}, {"method": "tool2", "description": "2"}],
        )
        
        manager.discover_and_add("s1", "tool1")
        manager.discover_and_add("s2", "tool2")
        
        _, s1_hot = manager.get_hot_counts("s1")
        _, s2_hot = manager.get_hot_counts("s2")
        
        assert s1_hot == 1
        assert s2_hot == 1
