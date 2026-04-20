"""Hot Tool Manager — manages LLM-accessible hot tool set.

Architecture:
  ┌─────────────────────────────────────────────────────────────┐
  │  LLM Tool Set = Fixed Core (7) + Hot Global + Hot Session   │
  │  + find_tool (escape hatch) + call_asset_method             │
  │                                                              │
  │  FIXED (always): exec_shell, read_file, write_file,...    │
  │  HOT GLOBAL (all sessions): warmed from static assets     │
  │  HOT SESSION (per-session): discovered via find_tool       │
  │  PERMANENT: find_tool (discovery), call_asset_method       │
  └─────────────────────────────────────────────────────────────┘
  
Asset visibility: RuntimeCenter queried into prompt (NOT tools)
Asset invocation: call_asset_method(asset_id, method, params)

Warming: Hot tools are "warmed" from static assets at startup.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── Fixed Core Tools (7 from OpenClaw) ─────────────────────────────────────

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
                "oldText": {"type": "string", "description": "要替换的原文本（必须精确匹配）"},
                "newText": {"type": "string", "description": "替换后的新文本"},
            },
            "required": ["path", "oldText", "newText"],
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


# ─── System Tools (always available) ─────────────────────────────────────────

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
]


# ─── Combined Fixed Tools ───────────────────────────────────────────────────

FIXED_TOOLS: list[dict[str, Any]] = FIXED_CORE_TOOLS + SYSTEM_TOOLS
FIXED_TOOL_NAMES: set[str] = {t["name"] for t in FIXED_TOOLS}


# ─── Dynamic Tool Registry ────────────────────────────────────────────────────

_DYNAMIC_REGISTRY: dict[str, dict[str, Any]] = {}


def _register_dynamic_tool(tool_def: dict[str, Any]) -> None:
    """Register a tool in global registry."""
    name = tool_def.get("name")
    if name:
        _DYNAMIC_REGISTRY[name] = tool_def
        logger.debug("Registered dynamic tool: %s", name)


def find_dynamic_tools(query: str) -> list[dict[str, Any]]:
    """Search dynamic tool registry."""
    query_lower = query.lower()
    results = []
    for name, tool in _DYNAMIC_REGISTRY.items():
        desc = tool.get("description", "")
        if query_lower in name.lower() or query_lower in desc.lower():
            results.append(tool)
    return results


# ─── HotToolManager ─────────────────────────────────────────────────────────

class HotToolManager:
    """Manages hot tool set for each session.
    
    Layers:
      - Fixed: 7 core + call_asset_method (always)
      - Hot Global: warmed from static assets at startup (all sessions)
      - Hot Session: discovered via find_tool (per-session)
      - Permanent: find_tool (discovery escape hatch)
    """

    def __init__(self) -> None:
        self._global_hot: set[str] = set()  # warmed at startup
        self._session_hot: dict[str, set[str]] = {}
        logger.info("HotToolManager initialized with %d fixed tools", len(FIXED_TOOLS))

    def warm_from_static_asset(
        self,
        asset_id: str,
        capabilities: list[dict[str, Any]],
    ) -> None:
        """Warm hot tools from static asset capabilities.
        
        Called at startup for static assets. Common methods become hot.
        """
        for cap in capabilities:
            method = cap.get("method", "")
            if not method or method.startswith("_"):
                continue
            tool_def = self._capability_to_tool(asset_id, cap)
            name = tool_def.get("name", "")
            if name:
                _register_dynamic_tool(tool_def)
                self._global_hot.add(name)
        logger.info("Warmed %d hot tools from %s", len(self._global_hot), asset_id)

    def _capability_to_tool(
        self,
        asset_id: str,
        cap: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert asset capability to tool definition."""
        method = cap.get("method", "")
        return {
            "name": f"{asset_id}:{method}",
            "description": cap.get("description", f"Call {method} on {asset_id}"),
            "parameters": cap.get("parameters", {
                "type": "object",
                "properties": {"params": {"type": "object", "description": "调用参数"}},
            }),
            "asset_id": asset_id,
            "method": method,
        }

    def mark_used(self, session_id: str, tool_name: str) -> None:
        """Mark a tool as used — adds to session hot set."""
        if session_id not in self._session_hot:
            self._session_hot[session_id] = set()
        if tool_name not in FIXED_TOOL_NAMES:
            self._session_hot[session_id].add(tool_name)
            logger.debug("Tool %s hot for session %s", tool_name, session_id)

    def get_tools_for_session(self, session_id: str) -> list[dict[str, Any]]:
        """Get complete tool set: fixed + global hot + session hot."""
        result = list(FIXED_TOOLS)
        names = set(FIXED_TOOL_NAMES)
        
        # Add global hot
        for name in self._global_hot:
            if name in _DYNAMIC_REGISTRY and name not in names:
                result.append(_DYNAMIC_REGISTRY[name])
                names.add(name)
        
        # Add session hot
        for name in self._session_hot.get(session_id, set()):
            if name in _DYNAMIC_REGISTRY and name not in names:
                result.append(_DYNAMIC_REGISTRY[name])
                names.add(name)
        
        return result

    def get_hot_counts(self, session_id: str) -> tuple[int, int]:
        """Return (global_hot_count, session_hot_count)."""
        return len(self._global_hot), len(self._session_hot.get(session_id, set()))

    def discover_and_add(self, session_id: str, query: str) -> list[str]:
        """Discover tools and add to session hot."""
        found = find_dynamic_tools(query)
        added = []
        for tool in found:
            name = tool.get("name")
            if name and name not in FIXED_TOOL_NAMES:
                self.mark_used(session_id, name)
                added.append(name)
        return added

    def clear_session(self, session_id: str) -> None:
        """Clear session hot (global hot preserved)."""
        self._session_hot.pop(session_id, None)
