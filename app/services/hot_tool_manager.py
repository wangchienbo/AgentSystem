"""Hot Tool Manager — manages which already-registered tool names are exposed.

Phase H boundary:
- ToolCallingEngine is the only tool registration/execution layer.
- HotToolManager only manages tool-name sets.
- No capability-level dynamic tool-name generation from assets.

Tool set shape:
  - Fixed core tools: always exposed
  - System asset tools: always exposed
  - Session hot tools: names of existing tools discovered/used in-session
  - find_tool: always available as the discovery escape hatch
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── Fixed Core Tools ────────────────────────────────────────────────────────

FIXED_CORE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "exec_shell",
        "description": "执行 shell 命令，返回命令输出。用于运行系统命令、脚本等。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"},
                "workdir": {"type": "string", "description": "工作目录（可选）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认60）"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "读取文件内容。用于查看代码、配置、文档等。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（绝对或相对路径）"},
                "limit": {"type": "integer", "description": "最大读取行数（可选）"},
                "offset": {"type": "integer", "description": "起始行号（可选）"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "写入或覆盖文件内容。用于创建新文件或覆盖已有文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "编辑文件（搜索替换）。用于对文件做精确修改。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_text": {"type": "string", "description": "要替换的原文本（必须精确匹配）"},
                "new_text": {"type": "string", "description": "替换后的新文本"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "list_files",
        "description": "列出目录内容。用于查看文件夹结构。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "搜索文件内容。用于在代码/文档中查找关键字。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "搜索模式（支持正则）"},
                "path": {"type": "string", "description": "搜索目录"},
                "file_pattern": {"type": "string", "description": "文件过滤模式，如 *.py"},
            },
            "required": ["pattern", "path"],
        },
    },
    {
        "name": "find_tool",
        "description": "搜索可用工具。当当前工具不够用时，用于查找更多工具。每次调用返回匹配的工具列表。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询，如 'file', 'http', 'browser'"},
            },
            "required": ["query"],
        },
    },
]


# ─── System Tools (always available) ────────────────────────────────────────

SYSTEM_TOOLS: list[dict[str, Any]] = [
    {
        "name": "call_asset_method",
        "description": "调用运行时资产的方法。所有系统资产（如 app_management, runtime_center）都通过此统一入口调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "资产ID，如 asset:app_management:v1"},
                "method": {"type": "string", "description": "要调用的方法名，如 start_app"},
                "params": {"type": "object", "description": "调用参数（可选）"},
            },
            "required": ["asset_id", "method"],
        },
    },
    {
        "name": "dispatch_app_task",
        "description": "【写操作】将 App 的写入型任务分发到 MasterControl 异步执行。适用于创建、修改、删除等有副作用的操作。工具立即返回 task_id，异步执行。注意：必须将用户提供的所有参数（如标题、题材等）填入 params 参数中。",
        "parameters": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "目标 App 标识，如 novel_studio"},
                "operation": {"type": "string", "description": "操作名，如 create_novel"},
                "params": {"type": "object", "description": "操作参数，必须包含用户提供的所有信息（如 title, genre 等）"},
                "parent_session": {"type": "string", "description": "交互层 session_id"},
            },
            "required": ["app", "operation", "params"],
        },
    },
    {
        "name": "query_task",
        "description": "查询 App 异步任务的执行状态。支持 poll 模式：若 status=pending/running 可稍后再查。",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务 ID"},
            },
            "required": ["task_id"],
        },
    },
]


FIXED_TOOLS: list[dict[str, Any]] = FIXED_CORE_TOOLS + SYSTEM_TOOLS
FIXED_TOOL_NAMES: set[str] = {t["name"] for t in FIXED_TOOLS}
_DYNAMIC_REGISTRY: dict[str, dict[str, Any]] = {t["name"]: t for t in FIXED_TOOLS}


def register_discoverable_tool(tool_def: dict[str, Any]) -> None:
    """Register an already-existing tool for discovery/hot exposure."""
    name = tool_def.get("name")
    if name:
        _DYNAMIC_REGISTRY[name] = tool_def
        logger.debug("Registered discoverable tool: %s", name)


def find_dynamic_tools(query: str) -> list[dict[str, Any]]:
    """Search registered tools by name/description."""
    query_lower = query.lower()
    results = []
    for name, tool in _DYNAMIC_REGISTRY.items():
        desc = tool.get("description", "")
        if query_lower in name.lower() or query_lower in desc.lower():
            results.append(tool)
    return results


class HotToolManager:
    """Manages fixed + session-local hot tool-name sets."""

    def __init__(self) -> None:
        self._session_hot: dict[str, set[str]] = {}
        logger.info("HotToolManager initialized with %d fixed tools", len(FIXED_TOOLS))

    def register_tool(self, tool_def: dict[str, Any], *, fixed: bool = False) -> None:
        """Register a tool definition for discovery.

        If fixed=True, the tool is already part of FIXED_TOOLS and this call is
        only treated as a registry refresh.
        """
        register_discoverable_tool(tool_def)
        if fixed:
            logger.debug("Refreshed fixed tool in discoverable registry: %s", tool_def.get("name"))

    def mark_used(self, session_id: str, tool_name: str) -> None:
        """Mark an already-registered tool as hot for a session."""
        if tool_name in FIXED_TOOL_NAMES:
            return
        if tool_name not in _DYNAMIC_REGISTRY:
            logger.debug("Ignoring unknown tool for session hot set: %s", tool_name)
            return
        self._session_hot.setdefault(session_id, set()).add(tool_name)
        logger.debug("Tool %s hot for session %s", tool_name, session_id)

    def get_tools_for_session(self, session_id: str) -> list[dict[str, Any]]:
        """Get complete tool set: fixed + session hot."""
        result = list(FIXED_TOOLS)
        names = set(FIXED_TOOL_NAMES)
        for name in self._session_hot.get(session_id, set()):
            if name in _DYNAMIC_REGISTRY and name not in names:
                result.append(_DYNAMIC_REGISTRY[name])
                names.add(name)
        return result

    def get_hot_counts(self, session_id: str) -> tuple[int, int]:
        """Return (fixed_count, session_hot_count)."""
        return len(FIXED_TOOLS), len(self._session_hot.get(session_id, set()))

    def discover_and_add(self, session_id: str, query: str) -> list[str]:
        """Discover already-registered tools and add matches to session hot."""
        found = find_dynamic_tools(query)
        added = []
        for tool in found:
            name = tool.get("name")
            if name and name not in FIXED_TOOL_NAMES:
                self.mark_used(session_id, name)
                added.append(name)
        return added

    def clear_session(self, session_id: str) -> None:
        """Clear session-local hot tools."""
        self._session_hot.pop(session_id, None)

