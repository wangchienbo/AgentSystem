"""Unified Tool Registry — central registry for all callable tools.

This registry consolidates:
- Skill-based tools (registered via SkillRpcService)
- Built-in tools (Python functions)
- Path-based flows (internal orchestrator flows, NOT exposed to LLM)
- External service tools

All tool discovery and invocation goes through this registry.
"""
from __future__ import annotations

from typing import Any

from app.models.tool_entry import ToolEntry, ToolType, ToolVisibility


class UnifiedToolRegistry:
    """Central tool registry with visibility and permission filtering."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def register(self, entry: ToolEntry) -> None:
        """Register a tool entry."""
        self._tools[entry.tool_id] = entry

    def unregister(self, tool_id: str) -> bool:
        """Remove a tool from the registry."""
        return self._tools.pop(tool_id, None) is not None

    def get(self, tool_id: str) -> ToolEntry | None:
        """Get a tool by ID."""
        entry = self._tools.get(tool_id)
        if entry and not entry.enabled:
            return None
        return entry

    def list_visible(
        self,
        user_id: str | None = None,
        app_id: str | None = None,
        user_role: str = "user",
        include_paths: bool = False,
    ) -> list[ToolEntry]:
        """List tools visible to the caller based on visibility rules.

        Args:
            user_id: Caller user ID
            app_id: Current app context
            user_role: Caller role level
            include_paths: Whether to include Path-type flows

        Returns:
            List of visible ToolEntry objects
        """
        visible = []
        for entry in self._tools.values():
            if not entry.enabled:
                continue

            # Path tools are NOT exposed to LLM by default
            if entry.tool_type == ToolType.PATH and not include_paths:
                continue

            # Visibility filter
            if entry.visibility == ToolVisibility.PRIVATE:
                if user_id and entry.app_id != user_id:
                    continue
            elif entry.visibility == ToolVisibility.APP:
                if app_id and entry.app_id != app_id:
                    continue

            # Permission filter
            if user_role < entry.owner_role:
                continue

            visible.append(entry)

        return visible

    def list_for_llm(
        self,
        user_id: str | None = None,
        app_id: str | None = None,
        user_role: str = "user",
    ) -> list[dict[str, Any]]:
        """List tools in LLM context format (excludes Paths)."""
        entries = self.list_visible(
            user_id=user_id,
            app_id=app_id,
            user_role=user_role,
            include_paths=False,
        )
        return [e.to_llm_context() for e in entries]

    def count(self) -> int:
        """Total registered tools."""
        return len(self._tools)
