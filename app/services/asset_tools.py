"""Asset-based tools for LLM integration.

Provides:
- query_asset_detail: let LLM look up full schema of a visible asset
- solidify_workflow:固化流程 from a sequence of steps
- execute_path_by_key: execute a path on a running App via its center skill
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.models.asset import Asset
from app.services.asset_registry import AssetRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions (for function-calling schema)
# ---------------------------------------------------------------------------

@dataclass
class ToolParam:
    name: str
    type: str
    description: str
    required: bool = True


@dataclass
class AssetToolDefinition:
    name: str
    description: str
    parameters: list[ToolParam] = field(default_factory=list)


def make_query_asset_detail_tool() -> AssetToolDefinition:
    return AssetToolDefinition(
        name="query_asset_detail",
        description="查询某个资产的详细使用说明，包括输入输出格式和注意事项",
        parameters=[
            ToolParam("asset_id", "string", "资产ID，例如 app.novel", required=True),
        ],
    )


def make_solidify_workflow_tool() -> AssetToolDefinition:
    return AssetToolDefinition(
        name="solidify_workflow",
        description="固化一个工作流程到指定 App，将步骤序列保存为可复用的 Path",
        parameters=[
            ToolParam("app_id", "string", "目标 App ID，例如 app.novel", required=True),
            ToolParam("path_key", "string", "流程 key，例如 write_chapter", required=True),
            ToolParam("steps", "array", "步骤序列，每个步骤是包含 skill_id 和 action 的字典", required=True),
        ],
    )


def make_execute_path_by_key_tool() -> AssetToolDefinition:
    return AssetToolDefinition(
        name="execute_path_by_key",
        description="按 key 调用中心 Skill 的固化流程",
        parameters=[
            ToolParam("app_id", "string", "目标 App ID，例如 app.novel", required=True),
            ToolParam("path_key", "string", "流程 key，例如 write_chapter", required=True),
            ToolParam("inputs", "object", "流程输入参数", required=True),
        ],
    )


def make_all_asset_tools() -> list[AssetToolDefinition]:
    return [
        make_query_asset_detail_tool(),
        make_solidify_workflow_tool(),
        make_execute_path_by_key_tool(),
    ]


# ---------------------------------------------------------------------------
# Asset Tool Executor
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str = ""


class AssetToolExecutor:
    """Execute asset-based tools.

    Bridges the LLM tool-call response to actual registry / orchestrator calls.
    """

    def __init__(self, registry: AssetRegistry, orchestrator_router: Any = None):
        """
        Args:
            registry: AssetRegistry instance
            orchestrator_router: callable(asset_id, path_key, inputs) -> result
                Routes execute_path_by_key to the correct App orchestrator.
        """
        self._registry = registry
        self._orchestrator_router = orchestrator_router

    def execute(self, tool_name: str, arguments: dict[str, Any], caller_name: str) -> ToolResult:
        try:
            if tool_name == "query_asset_detail":
                return self._query_asset_detail(arguments, caller_name)
            elif tool_name == "solidify_workflow":
                return self._solidify_workflow(arguments, caller_name)
            elif tool_name == "execute_path_by_key":
                return self._execute_path_by_key(arguments, caller_name)
            else:
                return ToolResult(success=False, error=f"Unknown asset tool: {tool_name}")
        except Exception as e:
            logger.exception("Asset tool execution failed: %s", tool_name)
            return ToolResult(success=False, error=str(e))

    def _query_asset_detail(self, args: dict, caller_name: str) -> ToolResult:
        asset_id = args.get("asset_id")
        if not asset_id:
            return ToolResult(success=False, error="asset_id is required")

        asset = self._registry.get_asset_detail(asset_id, caller_name)
        if asset is None:
            return ToolResult(success=False, error=f"Asset {asset_id} not found or not visible to {caller_name}")

        return ToolResult(success=True, data={
            "asset_id": asset.asset_id,
            "asset_type": asset.asset_type.value,
            "name": asset.name,
            "description": asset.description,
            "functions": [
                {
                    "key": f.key,
                    "name": f.name,
                    "description": f.description,
                    "input_schema": f.input_schema,
                    "output_schema": f.output_schema,
                    "notes": f.notes,
                }
                for f in asset.functions
            ],
            "metadata": asset.metadata,
        })

    def _solidify_workflow(self, args: dict, caller_name: str) -> ToolResult:
        app_id = args.get("app_id")
        path_key = args.get("path_key")
        steps = args.get("steps")

        if not app_id or not path_key or not steps:
            return ToolResult(success=False, error="app_id, path_key, and steps are required")

        # Verify caller has permission on the app
        asset = self._registry.get_asset_detail(app_id, caller_name)
        if asset is None:
            return ToolResult(success=False, error=f"App {app_id} not found or not visible")

        # Route to the app's orchestrator to solidify the path
        if self._orchestrator_router:
            try:
                result = self._orchestrator_router(app_id, "solidify", {
                    "path_key": path_key,
                    "steps": steps,
                })
                return ToolResult(success=True, data=result)
            except Exception as e:
                return ToolResult(success=False, error=f"Solidify failed: {e}")

        return ToolResult(success=False, error="Orchestrator router not configured")

    def _execute_path_by_key(self, args: dict, caller_name: str) -> ToolResult:
        app_id = args.get("app_id")
        path_key = args.get("path_key")
        inputs = args.get("inputs", {})

        if not app_id or not path_key:
            return ToolResult(success=False, error="app_id and path_key are required")

        # Verify visibility
        asset = self._registry.get_asset_detail(app_id, caller_name)
        if asset is None:
            return ToolResult(success=False, error=f"App {app_id} not found or not visible")

        # Route to the app's orchestrator
        if self._orchestrator_router:
            try:
                result = self._orchestrator_router(app_id, path_key, inputs)
                return ToolResult(success=True, data=result)
            except Exception as e:
                return ToolResult(success=False, error=f"Execution failed: {e}")

        return ToolResult(success=False, error="Orchestrator router not configured")


# ---------------------------------------------------------------------------
# Prompt assembler
# ---------------------------------------------------------------------------

def assemble_asset_overview_prompt(registry: AssetRegistry, caller_name: str) -> str:
    """Assemble a concise asset overview for LLM prompt injection."""
    assets = registry.get_visible_assets(caller_name)
    if not assets:
        return "当前没有可用的资产。"

    lines = ["你可用的资产："]
    for a in assets:
        lines.append(a.overview())
    lines.append("\n如需了解某个资产的详细使用说明（输入输出、注意事项），请调用 query_asset_detail(asset_id)。")
    return "\n".join(lines)
