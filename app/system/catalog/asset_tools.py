"""Asset-based tools for LLM integration.

Provides:
- query_asset_detail: let LLM look up full schema of a visible asset
- solidify_workflow:固化流程 from a sequence of steps
- execute_path_by_key: execute a path on a running App via its center skill
"""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.models.asset import Asset, AssetFunction
from app.models.asset_contract import AssetDescriptor
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
        description="查询某个资产的详细使用说明或运行态正式描述。优先返回运行态契约详情，静态资产作为兼容回退。",
        parameters=[
            ToolParam("asset_id", "string", "资产ID，例如 asset:runtime_center:v1、app.novel、skill.generic_writer", required=True),
        ],
    )


def make_execute_path_by_key_tool() -> AssetToolDefinition:
    return AssetToolDefinition(
        name="execute_path_by_key",
        description="在指定 app 上执行某个 path/function。",
        parameters=[
            ToolParam("app_id", "string", "目标 app 的 asset_id，例如 app.novel", required=True),
            ToolParam("path_key", "string", "要执行的 path/function key，例如 write_chapter", required=True),
            ToolParam("inputs", "object", "执行该 path 的输入参数", required=False),
        ],
    )


def make_solidify_workflow_tool() -> AssetToolDefinition:
    return AssetToolDefinition(
        name="solidify_workflow",
        description="把一组 skill step 固化成 app 上可复用的 workflow/path。",
        parameters=[
            ToolParam("app_id", "string", "目标 app 的 asset_id，例如 app.novel", required=True),
            ToolParam("path_key", "string", "要新增的 workflow/path key，例如 auto_write", required=True),
            ToolParam("steps", "array", "workflow steps，元素包含 skill_id 和 action", required=True),
        ],
    )


def make_list_assets_tool() -> AssetToolDefinition:
    return AssetToolDefinition(
        name="list_assets",
        description="列出当前可发现的运行态资产摘要。",
        parameters=[ToolParam("filter", "string", "可选过滤词", required=False)],
    )


def make_query_asset_info_tool() -> AssetToolDefinition:
    return AssetToolDefinition(
        name="query_asset_info",
        description="查询某个运行态资产的正式描述信息。",
        parameters=[ToolParam("asset_id", "string", "运行态资产ID", required=True)],
    )


def make_call_asset_method_tool() -> AssetToolDefinition:
    return AssetToolDefinition(
        name="call_asset_method",
        description="通过运行态资产安全映射入口调用某个资产方法。",
        parameters=[
            ToolParam("asset_id", "string", "运行态资产ID", required=True),
            ToolParam("method", "string", "能力方法名", required=True),
            ToolParam("params", "object", "调用参数", required=False),
        ],
    )


def make_all_asset_tools() -> list[AssetToolDefinition]:
    return [
        make_list_assets_tool(),
        make_query_asset_info_tool(),
        make_call_asset_method_tool(),
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

    def __init__(self, registry: AssetRegistry, orchestrator_router: Any = None, schema_registry: Any | None = None):
        """
        Args:
            registry: AssetRegistry instance
            orchestrator_router: callable(asset_id, path_key, inputs) -> result
                Routes execute_path_by_key to the correct App orchestrator.
            schema_registry: optional schema registry used to derive richer sample params
        """
        self._registry = registry
        self._orchestrator_router = orchestrator_router
        self._schema_registry = schema_registry

    def execute(self, tool_name: str, arguments: dict[str, Any], caller_name: str) -> ToolResult:
        try:
            if tool_name == "list_assets":
                return self._list_assets(arguments, caller_name)
            if tool_name == "query_asset_info":
                return self._query_asset_info(arguments, caller_name)
            if tool_name == "call_asset_method":
                return self._call_asset_method(arguments, caller_name)
            if tool_name == "query_asset_detail":
                return self._query_asset_detail(arguments, caller_name)
            if tool_name == "execute_path_by_key":
                return self._execute_path_by_key(arguments, caller_name)
            if tool_name == "solidify_workflow":
                return self._solidify_workflow(arguments, caller_name)
            return ToolResult(success=False, error=f"Unknown asset tool: {tool_name}")
        except Exception as e:
            logger.exception("Asset tool execution failed: %s", tool_name)
            return ToolResult(success=False, error=str(e))

    def _list_assets(self, args: dict, caller_name: str) -> ToolResult:
        if not hasattr(self._registry, "list_assets"):
            return ToolResult(success=False, error="Runtime asset listing is not available")
        filter_text = str(args.get("filter", "") or "").lower()
        items = []
        for asset in self._registry.list_assets():
            payload = asset.model_dump(mode="json") if hasattr(asset, "model_dump") else asset
            if filter_text and filter_text not in json.dumps(payload, ensure_ascii=False).lower():
                continue
            items.append(payload)
        return ToolResult(success=True, data=items)

    def _query_asset_info(self, args: dict, caller_name: str) -> ToolResult:
        asset_id = args.get("asset_id")
        if not asset_id:
            return ToolResult(success=False, error="asset_id is required")
        if not hasattr(self._registry, "query_asset_info"):
            return ToolResult(success=False, error="Runtime asset query is not available")
        result = self._registry.query_asset_info(asset_id)
        if result is None:
            return ToolResult(success=False, error=f"Asset {asset_id} not found")
        descriptor = dict(result)
        descriptor.setdefault("detail_level", "descriptor")
        return ToolResult(success=True, data=descriptor)

    def _call_asset_method(self, args: dict, caller_name: str) -> ToolResult:
        asset_id = args.get("asset_id")
        method = args.get("method")
        params = args.get("params") or {}
        if not asset_id or not method:
            return ToolResult(success=False, error="asset_id and method are required")
        if not hasattr(self._registry, "call_asset_method"):
            return ToolResult(success=False, error="Runtime asset call is not available")
        result = self._registry.call_asset_method(asset_id=asset_id, method=method, params=params)
        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        return ToolResult(success=ok, data=result, error="" if ok else str(result.get("error", "asset method call failed")))

    def _query_asset_detail(self, args: dict, caller_name: str) -> ToolResult:
        asset_id = args.get("asset_id")
        if not asset_id:
            return ToolResult(success=False, error="asset_id is required")

        if hasattr(self._registry, "query_asset_info"):
            runtime_detail = self._registry.query_asset_info(asset_id)
            if runtime_detail is not None:
                enriched = dict(runtime_detail)
                capabilities = [cap for cap in enriched.get("capabilities", []) if isinstance(cap, dict)]
                capability_methods = [cap.get("method") for cap in capabilities if cap.get("method")]
                enriched["detail_level"] = "expanded"
                enriched["capability_methods"] = capability_methods
                enriched["parameter_hints"] = {
                    cap.get("method"): {
                        "input_schema_ref": cap.get("input_schema_ref"),
                        "output_schema_ref": cap.get("output_schema_ref"),
                        "side_effect_level": cap.get("side_effect_level"),
                        "requires_runtime_alive": cap.get("requires_runtime_alive"),
                        "permission_hint": cap.get("permission_hint"),
                    }
                    for cap in capabilities if cap.get("method")
                }
                enriched["usage_notes"] = [
                    f"method={cap.get('method')} side_effect={cap.get('side_effect_level', 'read')} runtime_alive={cap.get('requires_runtime_alive', True)}"
                    for cap in capabilities if cap.get("method")
                ]
                enriched["capability_notes"] = {
                    cap.get("method"): cap.get("description", "")
                    for cap in capabilities if cap.get("method")
                }
                def _sample_value_from_schema(schema: dict[str, Any], prop_name: str | None = None) -> Any:
                    if not isinstance(schema, dict):
                        return "value"
                    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
                        return copy.deepcopy(schema["enum"][0])
                    schema_type = schema.get("type")
                    if isinstance(schema_type, list):
                        schema_type = next((item for item in schema_type if item != "null"), schema_type[0] if schema_type else None)
                    if schema_type == "object":
                        props = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
                        required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
                        keys = list(dict.fromkeys([*required, *props.keys()]))[:3]
                        return {
                            key: _sample_value_from_schema(props.get(key, {}), key)
                            for key in keys
                        }
                    if schema_type == "array":
                        item_schema = schema.get("items", {}) if isinstance(schema.get("items"), dict) else {}
                        return [_sample_value_from_schema(item_schema, prop_name)]
                    if schema_type == "boolean":
                        return True
                    if schema_type == "integer":
                        return 1
                    if schema_type == "number":
                        return 1.0
                    if schema_type == "null":
                        return None
                    if prop_name:
                        lowered_name = prop_name.lower()
                        if lowered_name.endswith("id") or lowered_name == "asset_id":
                            return asset_id
                        if "name" in lowered_name:
                            return "workspace_assistant"
                        if "method" in lowered_name:
                            return capability_methods[0] if capability_methods else "list_assets"
                        if "version" in lowered_name:
                            return "1.0.0"
                        if "user" in lowered_name or "owner" in lowered_name or "caller" in lowered_name:
                            return "system"
                        if "filter" in lowered_name:
                            return "runtime"
                        if "prompt" in lowered_name:
                            return "hello runtime"
                        if "modification" in lowered_name:
                            return "add runtime asset summary panel"
                    return "string" if schema_type == "string" else "value"

                def _sample_from_schema_ref(schema_ref: str | None) -> dict[str, Any]:
                    if not schema_ref or self._schema_registry is None:
                        return {}
                    try:
                        schema = self._schema_registry.resolve(schema_ref)
                    except Exception:
                        return {}
                    if not isinstance(schema, dict) or schema.get("type") != "object":
                        return {}
                    properties = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
                    required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
                    keys = list(dict.fromkeys([*required, *properties.keys()]))[:4]
                    return {
                        key: _sample_value_from_schema(properties.get(key, {}), key)
                        for key in keys
                    }

                def _example_params(method_name: str, hint: dict[str, Any]) -> dict[str, Any]:
                    sample_params: dict[str, Any] = _sample_from_schema_ref(hint.get("input_schema_ref"))
                    lowered = method_name.lower()
                    if "asset" in lowered:
                        sample_params.setdefault("asset_id", asset_id)
                    if lowered.startswith("query_") or lowered.startswith("get_"):
                        if "filter" in lowered:
                            sample_params.setdefault("filter", "runtime")
                    if "list_assets" == method_name:
                        sample_params.setdefault("filter_text", "runtime")
                    elif method_name == "query_asset_info":
                        sample_params.setdefault("asset_id", asset_id)
                    elif method_name == "call_asset_method":
                        sample_params.setdefault("asset_id", asset_id)
                        sample_params.setdefault("method", capability_methods[0] if capability_methods else "list_assets")
                        sample_params.setdefault("params", {})
                    elif method_name.startswith("resolve_"):
                        sample_params.setdefault("caller", "skill:test_skill")
                        sample_params.setdefault("complexity", "moderate")
                    elif method_name.startswith("package_"):
                        sample_params.setdefault("asset_id", "app.workspace.assistant")
                        if method_name == "package_rollback":
                            sample_params.setdefault("target_version", "1.0.0")
                    elif method_name.endswith("_app") or method_name in {"start_app", "stop_app", "delete_app", "uninstall_app", "query_app"}:
                        sample_params.setdefault("app_name", "workspace_assistant")
                    elif method_name == "show_permissions":
                        sample_params.setdefault("target_user", "system")
                    elif method_name == "refine_app":
                        sample_params.setdefault("app_name", "workspace_assistant")
                        sample_params.setdefault("modification", "add runtime asset summary panel")
                    if not sample_params and hint.get("input_schema_ref"):
                        sample_params["input_schema_ref"] = hint["input_schema_ref"]
                    return sample_params

                enriched["invoke_examples"] = [
                    {
                        "tool": "call_asset_method",
                        "arguments": {
                            "asset_id": asset_id,
                            "method": method,
                            "params": _example_params(method, enriched["parameter_hints"].get(method, {})),
                        },
                    }
                    for method in capability_methods[:5]
                ]
                return ToolResult(success=True, data=enriched)

        asset = self._registry.get_asset_detail(asset_id, caller_name)
        if asset is None:
            return ToolResult(success=False, error=f"Asset {asset_id} not found or not visible to {caller_name}")

        if isinstance(asset, AssetDescriptor):
            return ToolResult(success=True, data=asset.model_dump(mode="json"))

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

    def _execute_path_by_key(self, args: dict, caller_name: str) -> ToolResult:
        app_id = args.get("app_id")
        path_key = args.get("path_key")
        inputs = args.get("inputs") or {}

        if not app_id:
            return ToolResult(success=False, error="app_id is required")
        if not path_key:
            return ToolResult(success=False, error="path_key is required")
        if not callable(self._orchestrator_router):
            return ToolResult(success=False, error="orchestrator router is not configured")

        asset = self._registry.get_asset_detail(app_id, caller_name)
        if asset is None:
            return ToolResult(success=False, error=f"App {app_id} not found or not visible to {caller_name}")

        try:
            result = self._orchestrator_router(app_id, path_key, inputs)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=True, data=result)

    def _solidify_workflow(self, args: dict, caller_name: str) -> ToolResult:
        app_id = args.get("app_id")
        path_key = args.get("path_key")
        steps = args.get("steps") or []

        if not app_id:
            return ToolResult(success=False, error="app_id is required")
        if not path_key:
            return ToolResult(success=False, error="path_key is required")
        if not steps:
            return ToolResult(success=False, error="steps must not be empty")

        app_asset = self._registry.get_asset_detail(app_id, caller_name)
        if app_asset is None:
            return ToolResult(success=False, error=f"App {app_id} not found or not visible to {caller_name}")
        if getattr(app_asset, "asset_type", None).value != "app":
            return ToolResult(success=False, error=f"Asset {app_id} is not an app")

        existing = {f.key for f in getattr(app_asset, "functions", [])}
        if path_key not in existing:
            app_asset.add_function(AssetFunction(key=path_key, name=path_key, description="solidified workflow"))
            self._registry.register(app_asset)

        return ToolResult(success=True, data={
            "app_id": app_id,
            "path_key": path_key,
            "steps": steps,
            "solidified": True,
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
        "## 你可用的资产",
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
