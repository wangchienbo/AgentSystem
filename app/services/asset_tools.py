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
        description="查询某个资产的详细使用说明。\n"
                    "用法：当你在资产概览列表中看到一个感兴趣的资产，但不知道具体怎么使用时调用此工具。\n"
                    "返回内容：资产名称、描述、所有可用接口（function）的名称、说明、输入参数格式、输出格式、注意事项。\n"
                    "示例：query_asset_detail(asset_id='app.novel') → 返回小说 App 的 write_chapter 和 create_character 接口的完整使用说明",
        parameters=[
            ToolParam("asset_id", "string", "资产ID，例如 app.novel、skill.generic_writer、path.create_app", required=True),
        ],
    )





def make_all_asset_tools() -> list[AssetToolDefinition]:
    return [
        make_query_asset_detail_tool(),
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

        # Support both CatalogEntry (has .detail()) and Asset model
        if hasattr(asset, 'detail'):
            return ToolResult(success=True, data=asset.detail())

        # Fallback for old Asset model
        return ToolResult(success=True, data={
            "asset_id": asset.asset_id,
            "asset_type": asset.asset_type.value if hasattr(asset.asset_type, 'value') else str(asset.asset_type),
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
                for f in getattr(asset, 'functions', [])
            ],
            "metadata": getattr(asset, 'metadata', {}),
        })



# ---------------------------------------------------------------------------
# Prompt assembler
# ---------------------------------------------------------------------------

def assemble_asset_overview_prompt(registry: Any, caller_name: str) -> str:
    """Assemble a concise asset overview for LLM prompt injection.
    
    Compatible with both AssetRegistry (Asset model) and SystemCatalog (CatalogEntry).
    """
    assets = registry.get_visible_assets(caller_name)
    if not assets:
        return "当前没有可用的资产。"

    lines = [
        "## 可用资产概览",
        "",
        "以下是你可以调用的资产列表。每个资产包含：",
        "- asset_id: 资产唯一标识",
        "- 名称: 人类可读名称",
        "- 接口: 该资产提供的所有可调用的功能",
        "",
        "**重要：如需了解某个资产的详细使用说明（输入参数格式、输出格式、注意事项），",
        "请调用 query_asset_detail(asset_id) 工具。**",
        "",
    ]
    for a in assets:
        # Support both Asset model (has .functions) and CatalogEntry (has .interfaces)
        if hasattr(a, 'interfaces'):
            # CatalogEntry
            fn_names = ", ".join(f"{k}({v.get('description', '')})" for k, v in a.interfaces.items()) if a.interfaces else "无"
        elif hasattr(a, 'functions'):
            # Asset model
            fn_names = ", ".join(f"{f.key}({f.name})" for f in a.functions)
        else:
            fn_names = "无"
        lines.append(f"### {a.asset_id} ({a.name})")
        lines.append(f"描述: {a.description}")
        lines.append(f"可用接口: {fn_names if fn_names else '无'}")
        lines.append("")
    return "\n".join(lines)
