"""Package Management Tool — pip-like management for App/Skill/Path assets.

Core principle: source/ (development-time) and installed/ (runtime) are
physically separate. Modifying source/ does NOT affect running instances.
Only `build + install` promotes changes to the running system.

Provides tools for:
- package_list_installed: 列出已安装的包
- package_show: 查看包的详细信息
- package_build: 构建 source/ 中的包
- package_install: 安装已构建的包到 installed/
- package_uninstall: 卸载已安装的包
- package_rollback: 回滚到旧版本
- package_search: 搜索 source/ 中可用的包
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.asset_center import AssetCenter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@dataclass
class ToolParam:
    name: str
    type: str
    description: str
    required: bool = True


@dataclass
class PackageToolDefinition:
    name: str
    description: str
    parameters: list[ToolParam] = field(default_factory=list)


def make_package_list_installed_tool() -> PackageToolDefinition:
    return PackageToolDefinition(
        name="package_list_installed",
        description="列出 installed/ 中所有已安装的包（App/Skill/Path）。可按类型过滤。",
        parameters=[
            ToolParam("asset_type", "string", "过滤类型: app, skill, path。不传则返回全部。", required=False),
        ],
    )


def make_package_show_tool() -> PackageToolDefinition:
    return PackageToolDefinition(
        name="package_show",
        description="查看已安装包的详细信息（版本、构建hash、安装时间等）。",
        parameters=[
            ToolParam("asset_id", "string", "包ID。", required=True),
        ],
    )


def make_package_build_tool() -> PackageToolDefinition:
    return PackageToolDefinition(
        name="package_build",
        description="构建 source/ 中的资产定义，验证并打包到 build/。",
        parameters=[
            ToolParam("asset_id", "string", "要构建的资产ID，必须在 source/ 中存在。", required=True),
        ],
    )


def make_package_install_tool() -> PackageToolDefinition:
    return PackageToolDefinition(
        name="package_install",
        description="将已构建的包安装到 installed/（运行时层）。未指定 build_hash 时使用最新构建。",
        parameters=[
            ToolParam("asset_id", "string", "资产ID。", required=True),
            ToolParam("build_hash", "string", "可选，指定构建 hash。不传则使用最新。", required=False),
        ],
    )


def make_package_uninstall_tool() -> PackageToolDefinition:
    return PackageToolDefinition(
        name="package_uninstall",
        description="卸载已安装的包。仅移除 installed/，不影响 source/。",
        parameters=[
            ToolParam("asset_id", "string", "资产ID。", required=True),
        ],
    )


def make_package_rollback_tool() -> PackageToolDefinition:
    return PackageToolDefinition(
        name="package_rollback",
        description="回滚已安装的包到历史版本。",
        parameters=[
            ToolParam("asset_id", "string", "资产ID。", required=True),
            ToolParam("target_version", "string", "目标版本号，例如 1.0.0。", required=True),
        ],
    )


def make_package_search_tool() -> PackageToolDefinition:
    return PackageToolDefinition(
        name="package_search",
        description="搜索 source/ 中可用的资产定义（未安装的包）。",
        parameters=[
            ToolParam("query", "string", "搜索关键词（匹配 asset_id、name、description）。", required=True),
        ],
    )


def make_all_package_tools() -> list[PackageToolDefinition]:
    return [
        make_package_list_installed_tool(),
        make_package_show_tool(),
        make_package_build_tool(),
        make_package_install_tool(),
        make_package_uninstall_tool(),
        make_package_rollback_tool(),
        make_package_search_tool(),
    ]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str = ""


class PackageManagerExecutor:
    """Execute package management tools.

    Bridges LLM tool-call requests to AssetCenter operations.
    """

    def __init__(self, asset_center: AssetCenter):
        self._asset_center = asset_center

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            if tool_name == "package_list_installed":
                return self._list_installed(arguments)
            elif tool_name == "package_show":
                return self._show(arguments)
            elif tool_name == "package_build":
                return self._build(arguments)
            elif tool_name == "package_install":
                return self._install(arguments)
            elif tool_name == "package_uninstall":
                return self._uninstall(arguments)
            elif tool_name == "package_rollback":
                return self._rollback(arguments)
            elif tool_name == "package_search":
                return self._search(arguments)
            else:
                return ToolResult(success=False, error=f"Unknown package tool: {tool_name}")
        except Exception as e:
            logger.exception("Package tool execution failed: %s", tool_name)
            return ToolResult(success=False, error=str(e))

    def _list_installed(self, args: dict) -> ToolResult:
        asset_type = args.get("asset_type")
        installed = self._asset_center.list_installed(asset_type=asset_type)
        return ToolResult(success=True, data={"packages": installed, "count": len(installed)})

    def _show(self, args: dict) -> ToolResult:
        asset_id = args.get("asset_id")
        if not asset_id:
            return ToolResult(success=False, error="asset_id is required")

        # Show installed info
        installed_version = self._asset_center.get_installed_version(asset_id)
        # Show source info
        asset = self._asset_center.get_asset(asset_id)
        # Show build history
        history = self._asset_center.get_build_history(asset_id)

        info: dict[str, Any] = {"asset_id": asset_id}
        if asset:
            info["name"] = asset.name
            info["asset_type"] = asset.asset_type
            info["source_version"] = asset.version
            info["source_path"] = asset.source_path
            info["description"] = asset.description
        if installed_version:
            info["installed_version"] = installed_version
        info["build_history"] = [
            {"version": r.version, "build_hash": r.build_hash, "build_time": r.build_time, "source_hash": r.source_hash}
            for r in history
        ]
        return ToolResult(success=True, data=info)

    def _build(self, args: dict) -> ToolResult:
        asset_id = args.get("asset_id")
        if not asset_id:
            return ToolResult(success=False, error="asset_id is required")
        record = self._asset_center.build(asset_id)
        return ToolResult(success=True, data={
            "asset_id": record.asset_id,
            "version": record.version,
            "build_hash": record.build_hash,
            "build_time": record.build_time,
        })

    def _install(self, args: dict) -> ToolResult:
        asset_id = args.get("asset_id")
        if not asset_id:
            return ToolResult(success=False, error="asset_id is required")
        build_hash = args.get("build_hash")
        version = self._asset_center.install(asset_id, build_hash=build_hash)
        return ToolResult(success=True, data={
            "asset_id": asset_id,
            "installed_version": version,
            "build_hash": build_hash,
        })

    def _uninstall(self, args: dict) -> ToolResult:
        asset_id = args.get("asset_id")
        if not asset_id:
            return ToolResult(success=False, error="asset_id is required")
        self._asset_center.uninstall(asset_id)
        return ToolResult(success=True, data={"asset_id": asset_id, "status": "uninstalled"})

    def _rollback(self, args: dict) -> ToolResult:
        asset_id = args.get("asset_id")
        target_version = args.get("target_version")
        if not asset_id or not target_version:
            return ToolResult(success=False, error="asset_id and target_version are required")
        version = self._asset_center.rollback(asset_id, target_version)
        return ToolResult(success=True, data={
            "asset_id": asset_id,
            "rolled_back_to": version,
        })

    def _search(self, args: dict) -> ToolResult:
        query = args.get("query", "").lower()
        if not query:
            return ToolResult(success=False, error="query is required")

        assets = self._asset_center.list_assets()
        installed_ids = {item["asset_id"] for item in self._asset_center.list_installed()}

        results = []
        for a in assets:
            if (query in a.asset_id.lower()
                    or query in a.name.lower()
                    or query in a.description.lower()):
                results.append({
                    "asset_id": a.asset_id,
                    "name": a.name,
                    "asset_type": a.asset_type,
                    "version": a.version,
                    "description": a.description,
                    "installed": a.asset_id in installed_ids,
                    "source_path": a.source_path,
                })

        return ToolResult(success=True, data={"packages": results, "count": len(results)})
