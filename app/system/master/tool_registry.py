"""Tool Registry — defines all executable capabilities as tools.

Phase E.1: bridges rule-based handlers and LLM tool calling.
All Gateway handlers and system skills are registered here with schemas
the LLM can understand and select from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolParameter:
    """A single parameter definition for a tool."""
    name: str
    type: str  # "string", "integer", "boolean", "object"
    description: str
    required: bool = True
    enum: list[str] | None = None


@dataclass
class ToolDefinition:
    """A tool that the LLM can call."""
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    category: str = "general"  # app_lifecycle, app_management, permission, system, skill
    priority: int = 0  # higher = more likely to be suggested by LLM
    caller_ids: list[str] = field(default_factory=list)  # who can call this tool, empty = everyone
    owner_role: str = "system"  # system | admin | user


class ToolRegistry:
    """Registry of all available tools.

    Tools are defined with schemas so the LLM knows:
    - What each tool does
    - What parameters it needs
    - When to use it
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable] = {}
        self._build_default_tools()

    # -- default tools -------------------------------------------------------

    def _build_default_tools(self) -> None:
        """Register all Gateway handlers as tools."""

        # App Lifecycle
        self.register(ToolDefinition(
            name="create_app",
            description="根据用户需求创建一个新的 App。需要知道 App 类型或用途。",
            parameters=[
                ToolParameter("app_name", "string", "App 名称", required=False),
                ToolParameter("app_type", "string", "App 类型或用途，如：监控、日报、提醒、翻译", required=True),
                ToolParameter("description", "string", "App 的详细描述或需求", required=False),
            ],
            category="app_lifecycle",
            priority=10,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        self.register(ToolDefinition(
            name="start_app",
            description="启动一个已安装的 App。如果用户说'启动 XX'、'运行 XX'、'开启 XX'，使用此工具。",
            parameters=[
                ToolParameter("app_name", "string", "要启动的 App 名称", required=True),
            ],
            category="app_lifecycle",
            priority=10,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        self.register(ToolDefinition(
            name="stop_app",
            description="停止一个正在运行的 App。",
            parameters=[
                ToolParameter("app_name", "string", "要停止的 App 名称", required=True),
            ],
            category="app_lifecycle",
            priority=8,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        self.register(ToolDefinition(
            name="pause_app",
            description="暂停一个正在运行的 App（可恢复）。",
            parameters=[
                ToolParameter("app_name", "string", "要暂停的 App 名称", required=True),
            ],
            category="app_lifecycle",
            priority=5,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        self.register(ToolDefinition(
            name="resume_app",
            description="恢复一个已暂停的 App。",
            parameters=[
                ToolParameter("app_name", "string", "要恢复的 App 名称", required=True),
            ],
            category="app_lifecycle",
            priority=5,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        # App Management
        self.register(ToolDefinition(
            name="list_apps",
            description="列出用户的所有 App，可按状态过滤。用户说'看看我的App'、'有哪些App'、'App列表'时使用。",
            parameters=[
                ToolParameter("status", "string", "过滤状态：running/stopped/paused/all", required=False, enum=["running", "stopped", "paused", "all"]),
            ],
            category="app_management",
            priority=8,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        self.register(ToolDefinition(
            name="query_app",
            description="查询某个 App 的详细信息、状态或运行结果。",
            parameters=[
                ToolParameter("app_name", "string", "要查询的 App 名称", required=True),
            ],
            category="app_management",
            priority=7,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        self.register(ToolDefinition(
            name="modify_app",
            description="修改已有 App 的配置、参数或行为。",
            parameters=[
                ToolParameter("app_name", "string", "要修改的 App 名称", required=True),
                ToolParameter("modification", "string", "要修改的内容或新的配置", required=True),
            ],
            category="app_management",
            priority=6,
            caller_ids=["system.master", "system.gateway"],
        ))

        self.register(ToolDefinition(
            name="delete_app",
            description="删除一个 App。需要用户确认。",
            parameters=[
                ToolParameter("app_name", "string", "要删除的 App 名称", required=True),
            ],
            category="app_management",
            priority=3,
            caller_ids=["system.master", "system.gateway"],
        ))

        # Interactive App
        self.register(ToolDefinition(
            name="modify_interactive_app",
            description="修改聊天界面的 UI，如主题、样式、布局、颜色、添加组件等。用户说'改一下界面'、'换个主题'、'加个按钮'时使用。",
            parameters=[
                ToolParameter("modification_type", "string", "修改类型：theme/layout/component/style", required=True),
                ToolParameter("description", "string", "具体的修改描述", required=True),
            ],
            category="app_management",
            priority=5,
            caller_ids=["system.master", "system.gateway"],
        ))

        # Permission Management
        self.register(ToolDefinition(
            name="grant_admin",
            description="将某个用户提升为 admin 角色。只有 root 或 admin 可以执行。",
            parameters=[
                ToolParameter("target_user", "string", "要提升的用户名或用户ID", required=True),
            ],
            category="permission",
            priority=7,
            caller_ids=["system.master"],
        ))

        self.register(ToolDefinition(
            name="grant_root",
            description="将某个用户提升为 root 角色。只有 root 可以执行。",
            parameters=[
                ToolParameter("target_user", "string", "要提升的用户名或用户ID", required=True),
            ],
            category="permission",
            priority=5,
            caller_ids=["system.master"],
        ))

        self.register(ToolDefinition(
            name="revoke_role",
            description="撤销某个用户的 admin/root 角色，降级为普通用户。",
            parameters=[
                ToolParameter("target_user", "string", "要降级的用户名或用户ID", required=True),
            ],
            category="permission",
            priority=6,
            caller_ids=["system.master"],
        ))

        self.register(ToolDefinition(
            name="show_permissions",
            description="查看某个用户的权限信息。如果不指定用户，默认查看当前用户自己的权限。",
            parameters=[
                ToolParameter("target_user", "string", "要查询的用户名，留空表示查自己", required=False),
            ],
            category="permission",
            priority=8,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        self.register(ToolDefinition(
            name="list_users",
            description="列出系统中的所有用户。",
            parameters=[],
            category="permission",
            priority=6,
            caller_ids=["system.master", "system.gateway"],
        ))

        # System
        self.register(ToolDefinition(
            name="query_status",
            description="查询系统整体运行状态、健康情况。用户说'系统状态'、'运行情况'时使用。",
            parameters=[],
            category="system",
            priority=7,
            caller_ids=["system.master", "system.gateway"],
        ))

        self.register(ToolDefinition(
            name="query_help",
            description="展示系统能帮助的功能列表和使用方式。用户说'帮助'、'能做什么'、'功能'时使用。",
            parameters=[],
            category="system",
            priority=5,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        self.register(ToolDefinition(
            name="greet",
            description="用户打招呼时的回复。包含自我介绍和 App 概况。",
            parameters=[],
            category="system",
            priority=3,
            caller_ids=["system.master", "system.gateway", "app.*"],
        ))

        # Master Control — optional tool for system-level operations
        # LLM decides when to call this for operations beyond simple interaction
        self.register(ToolDefinition(
            name="master_execute",
            description=(
                "主控系统级操作入口。当需要执行系统级变更时使用："
                "创建/修改/删除 App 或 Skill、权限管理、系统升级、提交系统建议等。"
                "简单查询、格式化、闲聊不需要调用。"
            ),
            parameters=[
                ToolParameter("operation", "string", "操作类型，如 create_app, modify_app, grant_admin, suggest 等", required=True),
                ToolParameter("target", "string", "操作目标（App 名称、Skill ID 等）", required=False),
                ToolParameter("params", "object", "操作参数，具体取决于 operation", required=False),
            ],
            category="system",
            priority=9,  # high priority — LLM should see this first for system ops
            caller_ids=["system.master", "system.gateway"],
        ))

    # -- registration API ----------------------------------------------------

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool

    def register_handler(self, tool_name: str, handler: Callable) -> None:
        """Register a handler function for a tool."""
        self._handlers[tool_name] = handler

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def get_handler(self, name: str) -> Callable | None:
        """Get the handler function for a tool."""
        return self._handlers.get(name)

    def list_all(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        """List tools in a specific category."""
        return [t for t in self._tools.values() if t.category == category]

    # -- caller_ids permission filtering --------------------------------------

    @staticmethod
    def _match_caller(caller_id: str, allowed_callers: list[str]) -> bool:
        """Check if a caller_id is allowed by the caller_ids list.

        Supports wildcard patterns:
          "app.*" matches any caller_id starting with "app."
          "app.novel" matches exactly
        """
        if not allowed_callers:
            return True  # empty caller_ids = everyone can call
        for pattern in allowed_callers:
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if caller_id.startswith(prefix):
                    return True
            elif caller_id == pattern:
                return True
        return False

    def get_tools_for_caller(self, caller_id: str) -> list[ToolDefinition]:
        """Get only the tools that the given caller_id is allowed to call."""
        return [
            t for t in self._tools.values()
            if self._match_caller(caller_id, t.caller_ids)
        ]

    def can_call(self, caller_id: str, tool_name: str) -> bool:
        """Check if a caller_id is allowed to call a specific tool."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return False
        return self._match_caller(caller_id, tool.caller_ids)

    # -- LLM prompt generation -----------------------------------------------

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Convert tools to OpenAI function calling format."""
        tools = []
        for tool in self._tools.values():
            properties = {}
            required = []
            for param in tool.parameters:
                prop: dict[str, Any] = {
                    "type": param.type,
                    "description": param.description,
                }
                if param.enum:
                    prop["enum"] = param.enum
                properties[param.name] = prop
                if param.required:
                    required.append(param.name)

            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        return tools

    def to_prompt_text(self, include_descriptions: bool = True) -> str:
        """Generate a text description of all tools for the LLM prompt.

        Used when function calling is not available (cheaper models).
        """
        lines = ["## 可用工具列表\n"]
        by_category: dict[str, list[ToolDefinition]] = {}
        for tool in sorted(self._tools.values(), key=lambda t: -t.priority):
            by_category.setdefault(tool.category, []).append(tool)

        category_names = {
            "app_lifecycle": "🔨 App 生命周期",
            "app_management": "📱 App 管理",
            "permission": "🔐 权限管理",
            "system": "⚙️ 系统",
        }

        for cat, cat_tools in by_category.items():
            cat_name = category_names.get(cat, cat)
            lines.append(f"\n{cat_name}:")
            for tool in cat_tools:
                if include_descriptions:
                    lines.append(f"- **{tool.name}**: {tool.description}")
                    if tool.parameters:
                        params = ", ".join(p.name for p in tool.parameters if p.required)
                        if params:
                            lines.append(f"  必需参数: {params}")
                else:
                    lines.append(f"- {tool.name}")

        return "\n".join(lines)
