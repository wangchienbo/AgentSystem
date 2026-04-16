"""Skill Registry Service — bridges Skill RPC definitions into the Unified Tool Registry.

This service:
1. Loads skill manifests from installed/ directories
2. Converts each skill into a ToolEntry
3. Registers them in the UnifiedToolRegistry
4. Handles skill lifecycle (load/unload/reload)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.models.tool_entry import ToolEntry, ToolType, ToolVisibility, ToolParameter
from app.services.skill_rpc import SkillRpcService
from app.services.unified_tool_registry import UnifiedToolRegistry

logger = logging.getLogger(__name__)


class SkillRegistryService:
    """Manages skill registration from installed definitions into the tool registry."""

    def __init__(
        self,
        installed_dir: str = "installed",
        rpc_service: SkillRpcService | None = None,
        tool_registry: UnifiedToolRegistry | None = None,
    ) -> None:
        self._installed_dir = Path(installed_dir)
        self._rpc_service = rpc_service
        self._tool_registry = tool_registry
        self._registered_skills: set[str] = set()

    def set_dependencies(
        self,
        rpc_service: SkillRpcService,
        tool_registry: UnifiedToolRegistry,
    ) -> None:
        """Inject dependencies (for cases where they're created later)."""
        self._rpc_service = rpc_service
        self._tool_registry = tool_registry

    # ---- Discovery & Registration ----

    def discover_and_register(self, owner_id: str = "system") -> list[str]:
        """Scan installed/ directory and register all skills as tools."""
        if not self._installed_dir.exists():
            logger.warning("Installed dir not found: %s", self._installed_dir)
            return []

        registered = []
        for skill_dir in self._installed_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            manifest_path = skill_dir / "installed.json"
            if not manifest_path.exists():
                manifest_path = skill_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                skill_id = manifest.get("skill_id", manifest.get("asset_id", skill_dir.name))
                if skill_id in self._registered_skills:
                    continue

                entry = self._build_tool_entry(skill_id, manifest, owner_id)
                if self._tool_registry:
                    self._tool_registry.register(entry)
                self._registered_skills.add(skill_id)
                registered.append(skill_id)
                logger.info("Registered skill as tool: %s", skill_id)
            except Exception as e:
                logger.error("Failed to register skill from %s: %s", skill_dir, e)

        return registered

    def _build_tool_entry(
        self,
        skill_id: str,
        manifest: dict[str, Any],
        owner_id: str,
    ) -> ToolEntry:
        """Convert a skill manifest into a ToolEntry."""
        # Create a callable handler that routes through SkillRpcService
        handler = None
        if self._rpc_service:
            async def _rpc_handler(**kwargs):
                return await self._rpc_service.call(
                    skill_id=skill_id,
                    action="execute",
                    payload=kwargs,
                    caller_id=owner_id,
                )
            handler = _rpc_handler

        parameters = []
        input_schema = manifest.get("input_schema", {})
        for param_name, param_def in input_schema.get("properties", {}).items():
            parameters.append(ToolParameter(
                name=param_name,
                param_type=param_def.get("type", "string"),
                description=param_def.get("description", ""),
                required=param_name in input_schema.get("required", []),
            ))

        return ToolEntry(
            tool_id=skill_id,
            name=manifest.get("name", skill_id),
            tool_type=ToolType.SKILL,
            description=manifest.get("description", ""),
            parameters=parameters,
            handler=handler,
            visibility=ToolVisibility.PUBLIC if owner_id == "system" else ToolVisibility.PRIVATE,
            app_id=owner_id if owner_id != "system" else None,
            tags=manifest.get("tags", []),
            version=manifest.get("version", "1.0.0"),
        )

    def unregister(self, skill_id: str) -> bool:
        """Unregister a skill from the tool registry."""
        if self._tool_registry:
            result = self._tool_registry.unregister(skill_id)
            if result:
                self._registered_skills.discard(skill_id)
            return result
        return False

    def list_registered(self) -> list[str]:
        return sorted(self._registered_skills)
