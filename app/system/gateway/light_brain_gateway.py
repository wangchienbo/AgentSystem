"""LightBrain Gateway — the unified interaction entry point.

Orchestrates: receive message → interpret intent → execute workflow → serialize reply.
Phase 8.1: rule-based interpreter, basic workflow execution, structured replies.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.chat import (
    ActionSuggestion,
    ChatMessageRequest,
    ChatMessageResponse,
    InlineItem,
    InterpretedCommand,
)
from app.services.light_brain_memory import LightBrainMemory, LightBrainMemoryError
from app.services.light_brain_interpreter import LightBrainInterpreter
from app.services.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class LightBrainGateway:
    """Unified entry point: message → intent → execution → reply."""

    RUNTIME_ASSET_TOOL_INTENTS = {"list_assets", "query_asset_info", "call_asset_method", "query_asset_detail"}

    def __init__(
        self,
        memory: LightBrainMemory,
        interpreter: LightBrainInterpreter,
        skill_runner=None,
        lifecycle=None,
        log_center=None,
        persistence=None,
        permission_skill=None,
        permission_validator=None,
        package_manager_executor=None,
        asset_tool_executor=None,
        interactive_app_workflow=None,
        master_control=None,
        app_catalog=None,  # Legacy compatibility (replaced by set_catalog)
        # Legacy kwarg aliases for backward compatibility
        app_registry_service=None,
        app_lifecycle_service=None,
        app_runtime_host=None,
        persistence_service=None,
        **extra_deps,
    ):
        self._memory = memory
        self._interpreter = interpreter
        self._skill_runner = skill_runner
        self._lifecycle = lifecycle or app_lifecycle_service  # legacy alias
        self._log_center = log_center
        self._persistence = persistence or persistence_service  # legacy alias
        self._permission_skill = permission_skill
        self._permission_validator = permission_validator
        self._package_manager_executor = package_manager_executor
        self._asset_tool_executor = asset_tool_executor
        self._interactive_app_workflow = interactive_app_workflow
        self._master_control = master_control
        self._app_registry: Any | None = app_registry_service  # legacy alias
        self._orchestrator_bridge: Any | None = None
        self._runtime_host: Any | None = app_runtime_host  # legacy alias
        self._catalog: Any | None = None
        self._app_lifecycle_query_executor: Any | None = None
        self._app_presenter: Any | None = None
        self._app_command_service: Any | None = None
        self._name: str | None = None

        # Legacy: accept app_catalog as initial value
        if app_catalog is not None:
            self._catalog = app_catalog

        # Phase 6.1: load session history into memory
        # Legacy note: if persistence is a PersistenceService, it handles its own
        # restore via restore_state() — we skip the memory restore here.
        if self._persistence is not None and hasattr(self._persistence, "load_state"):
            self._memory.restore_from(self._persistence.load_state())
        self._load_identity()

        # Tool registry for structured skill selection
        self._tool_registry = self._build_default_tool_registry()

        # Built-in intent → handler mapping
        self._handlers: dict[str, Any] = {
            "greet": self._handle_greet,
            "query_status": self._handle_query_status,
            "query_help": self._handle_query_help,
            "grant_admin": self._handle_permission,
            "grant_root": self._handle_permission,
            "revoke_role": self._handle_permission,
            "show_permissions": self._handle_permission,
            "list_users": self._handle_permission,
            "show_self": self._handle_permission,
            "list_assets": self._handle_runtime_asset_tool,
            "query_asset_info": self._handle_runtime_asset_tool,
            "call_asset_method": self._handle_runtime_asset_tool,
            "query_asset_detail": self._handle_query_asset_detail,
        }

    def set_app_registry(self, app_registry: Any) -> None:
        """Inject AppRegistry for local handlers."""
        self._app_registry = app_registry

    def set_orchestrator_bridge(self, bridge: Any) -> None:
        """Inject GatewayOrchestratorBridge for orchestrated command path."""
        self._orchestrator_bridge = bridge

    def set_runtime_host(self, runtime_host: Any) -> None:
        """Inject RuntimeHost for lifecycle operations."""
        self._runtime_host = runtime_host

    def set_catalog(self, catalog: Any) -> None:
        """Inject SystemCatalog for static catalog operations."""
        self._catalog = catalog

    async def receive_message(
        self,
        request: ChatMessageRequest,
        available_apps: list[dict[str, Any]] | None = None,
        log_center=None,
        **extra_deps: Any,
    ) -> ChatMessageResponse:
        """Entry point: handles a single incoming message."""
        session_id = request.session_id or str(uuid.uuid4())

        # Phase 5.1: create or get session (ensures persistence)
        self._memory.create_session(
            user_id=request.user_id,
            channel=request.channel,
            session_id=session_id,
        )
        self._memory.record_user_message(session_id, request.message)

        # Phase 7.1: interpret intent using interpreter
        command = self._interpreter.interpret(
            request.message,
            available_apps=available_apps or [],
            user_id=request.user_id,
        )

        # Phase 7.2: enrich command with tools and session state
        available_apps = available_apps or []
        command = self._enrich_command(command, session_id, available_apps)
        self._memory.record_command(session_id, command)

        # Phase 7.3: execute workflow and return reply
        result = await self._execute_command(command, session_id, available_apps)
        self._memory.record_reply(session_id, result)

        # Phase 7.5: auto-save state if persistence available
        self._auto_save()

        return result

    # Backward compatibility alias
    process_message = receive_message

    def _enrich_command(
        self,
        command: InterpretedCommand,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> InterpretedCommand:
        """Enrich command with session context and available tools."""
        # Add available apps as context
        command.context["available_apps"] = available_apps

        # Add tool registry as context
        command.context["tool_registry"] = self._tool_registry

        # Phase 5.1: check memory for similar past interactions
        if self._memory:
            similar = self._memory.find_similar(command.raw_input, limit=3)
            if similar:
                command.context["similar_past_interactions"] = similar

        return command

    async def _execute_command(
        self,
        command: InterpretedCommand,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> ChatMessageResponse:
        """Dispatch command to appropriate handler or skill."""
        # Bridge-side handler dispatch first
        bridge_eligible_intents = {
            "create_app", "start_app", "stop_app", "pause_app",
            "resume_app", "query_app", "list_apps", "delete_app", "modify_app",
        }
        if (
            self._orchestrator_bridge
            and self._orchestrator_bridge.is_available()
            and command.intent in bridge_eligible_intents
            and command.intent not in {"greet", "query_help", "query_status"}
        ):
            try:
                bridge_result = await self._orchestrator_bridge.execute_command(
                    user_id=command.user_id or "",
                    app_instance_id="default",
                    text=command.raw_input or "",
                    session_id=session_id,
                )
                if bridge_result is not None:
                    return ChatMessageResponse(
                        type=bridge_result.get("type", "text"),
                        content=bridge_result.get("content", ""),
                        session_id=session_id,
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Bridge execution failed: %s", e,
                )

        # Local handler dispatch
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "我没理解你的意思，换个说法试试？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        local_handlers = {
            "greet": self._handle_greet,
            "query_status": self._handle_query_status,
            "query_help": self._handle_query_help,
            "grant_admin": self._handle_permission,
            "grant_root": self._handle_permission,
            "revoke_role": self._handle_permission,
            "show_permissions": self._handle_permission,
            "list_users": self._handle_permission,
            "show_self": self._handle_permission,
            "list_assets": self._handle_runtime_asset_tool,
            "query_asset_info": self._handle_runtime_asset_tool,
            "call_asset_method": self._handle_runtime_asset_tool,
            "query_asset_detail": self._handle_query_asset_detail,
            "modify_interactive_app": self._handle_modify_interactive_app,
            "self_modify": self._handle_modify_interactive_app,
            "grant_admin": self._handle_permission,
            "grant_root": self._handle_permission,
            "revoke_role": self._handle_permission,
            "show_permissions": self._handle_permission,
            "list_users": self._handle_permission,
            "show_self": self._handle_permission,
            "list_apps": self._handle_list_apps,
            "cancel": self._handle_cancel,
            "query_asset_detail": self._handle_query_asset_detail,
            "package_list_installed": self._handle_package_list_installed,
            "package_show": self._handle_package_show,
            "package_build": self._handle_package_build,
            "package_install": self._handle_package_install,
            "package_uninstall": self._handle_package_uninstall,
            "package_rollback": self._handle_package_rollback,
            "package_search": self._handle_package_search,
            "master_execute": self._handle_master_execute,
        }

        handler = local_handlers.get(command.intent)
        if handler:
            return await handler(command, session_id, available_apps)

        return self._error_reply(session_id, f"我还不会处理这个指令。试试说创建 App 或看看我的 App。")

    def _build_default_tool_registry(self):
        from app.services.tool_registry import ToolRegistry, ToolDefinition, ToolParameter
        registry = ToolRegistry()

        registry.register(ToolDefinition(
            name="list_assets",
            description="列出当前运行态可发现资产。用户说‘现在有什么资产’、‘你能操作什么’时使用。",
            parameters=[ToolParameter("filter", "string", "可选过滤词", required=False)],
            category="asset", priority=9,
        ))
        registry.register(ToolDefinition(
            name="query_asset_info",
            description="查询某个运行态资产的详细描述、状态和能力。",
            parameters=[ToolParameter("asset_id", "string", "资产ID", required=True)],
            category="asset", priority=9,
        ))
        registry.register(ToolDefinition(
            name="call_asset_method",
            description="通过安全映射入口调用某个运行态资产方法。",
            parameters=[
                ToolParameter("asset_id", "string", "资产ID", required=True),
                ToolParameter("method", "string", "方法名", required=True),
                ToolParameter("params", "object", "调用参数", required=False),
            ],
            category="asset", priority=8,
        ))
        registry.register(ToolDefinition(
            name="query_asset_detail",
            description="查询资产详细使用说明或详细契约。",
            parameters=[ToolParameter("asset_id", "string", "资产ID", required=True)],
            category="asset", priority=7,
        ))

        registry.register(ToolDefinition(
            name="start_app",
            description="启动一个已安装的 App。用户说'启动XX'、'运行XX'、'开启XX'时使用。",
            parameters=[ToolParameter("app_name", "string", "要启动的 App 名称", required=True)],
            category="app_lifecycle", priority=10,
        ))
        registry.register(ToolDefinition(
            name="stop_app",
            description="停止一个正在运行的 App。用户说'停止XX'、'关闭XX'时使用。",
            parameters=[ToolParameter("app_name", "string", "要停止的 App 名称", required=True)],
            category="app_lifecycle", priority=8,
        ))
        registry.register(ToolDefinition(
            name="create_app",
            description="根据用户需求创建一个新的 App。",
            parameters=[
                ToolParameter("app_type", "string", "App 类型或用途", required=True),
                ToolParameter("description", "string", "App 的详细描述", required=False),
            ],
            category="app_lifecycle", priority=9,
        ))
        registry.register(ToolDefinition(
            name="list_apps",
            description="列出用户的所有 App。用户说'看看我的App'、'App列表'时使用。",
            parameters=[],
            category="app_management", priority=7,
        ))
        registry.register(ToolDefinition(
            name="query_app",
            description="查询某个 App 的详细信息或状态。",
            parameters=[ToolParameter("app_name", "string", "要查询的 App 名称", required=True)],
            category="app_management", priority=6,
        ))
        registry.register(ToolDefinition(
            name="show_permissions",
            description="查看某个用户的权限。如果不指定用户，查看当前用户自己的权限。",
            parameters=[ToolParameter("target_user", "string", "要查询的用户，留空表示自己", required=False)],
            category="permission", priority=8,
        ))
        registry.register(ToolDefinition(
            name="list_users",
            description="列出系统中的所有用户。",
            parameters=[],
            category="permission", priority=6,
        ))
        registry.register(ToolDefinition(
            name="query_status",
            description="查询系统整体运行状态。用户说'系统状态'、'运行情况'时使用。",
            parameters=[],
            category="system", priority=7,
        ))

        return registry

    def _load_identity(self) -> None:
        import os
        identity_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "lightbrain", "identity.json")
        os.makedirs(os.path.dirname(identity_path), exist_ok=True)
        if os.path.exists(identity_path):
            with open(identity_path) as f:
                data = json.load(f)
                self._name = data.get("name")
        if not self._name:
            import random
            prefixes = ["星", "渊", "岚", "溯", "曜", "穹", "澈", "翎", "朔", "玄", "霁", "衡"]
            suffixes = ["枢", "鉴", "策", "弈", "衡", "衍", "序", "衍", "弦", "翎"]
            self._name = random.choice(prefixes) + random.choice(suffixes)
            with open(identity_path, "w") as f:
                json.dump({"name": self._name, "role": "agent-system-interface"}, f)

    async def _handle_greet(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        running = [a for a in apps if a.get("status") == "running"]
        total = len(apps)
        capabilities = self._enumerate_capabilities()
        self_desc = "我是一套 Agent 驱动的系统，我的职责是：\n\n" + capabilities
        app_status = f"\n当前有 {total} 个 App"
        if running:
            app_status += f"，其中 {len(running)} 个在运行"
        name_line = f"你可以叫我「{self._name}」。\n\n" if self._name else ""
        return ChatMessageResponse(
            type="text",
            content=f"你好！{self_desc}{app_status}\n\n"
                    f"{name_line}"
                    f"你可以对我说：\n"
                    f'• "帮我建一个监控 App"\n'
                    f'• "看看我的 App 列表"\n'
                    f'• "启动 XX App"\n'
                    f'• "系统状态怎么样"',
            session_id=session_id,
            actions=command.suggested_actions,
        )

    def _enumerate_capabilities(self) -> str:
        caps = []
        handler_intents = set(self._handlers.keys())

        if "create_app" in handler_intents:
            caps.append("🔨 根据你的需求，创建并配置各种功能 App")
        if "list_apps" in handler_intents:
            caps.append("📱 管理你所有的 App —— 查看、启动、停止、暂停、恢复、修改、删除")
        if "query_status" in handler_intents:
            caps.append("📊 汇报系统的整体运行状态")
        if "query_help" in handler_intents:
            caps.append("❓ 回答你关于我能力的问题")
        if "query_app" in handler_intents:
            caps.append("🔍 查询单个 App 的详细信息")
        if not caps:
            caps.append("处理你的指令，管理 App 的生命周期")
        return "\n".join(caps)

    async def _handle_query_status(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if command.target_app:
            target = self._resolve_instance_id(command.target_app)
            display_name = self._resolve_display_name(target, command.target_app)

            if self._app_lifecycle_query_executor:
                try:
                    resolution = await self._app_lifecycle_query_executor._resolve_app_operation(target, display_name)
                    if resolution.static_found or resolution.runtime_found:
                        runtime_status = resolution.runtime_status
                        static_status = resolution.static_status
                        effective_status = runtime_status if runtime_status != "not_running" else static_status
                        status_icons = {"running": "🟢", "paused": "🟡", "stopped": "🔴", "installed": "🔵", "active": "🔵", "error": "⛔", "not_running": "⚪"}
                        icon = status_icons.get(effective_status, "⚪")
                        status_labels = {"running": "运行中", "paused": "已暂停", "stopped": "已停止", "installed": "已安装", "active": "已安装", "error": "故障", "not_running": "未运行"}
                        label = status_labels.get(effective_status, effective_status)
                        actions = []
                        if runtime_status == "running":
                            actions = [
                                ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": display_name}, style="danger"),
                                ActionSuggestion(id="pause", label="⏸ 暂停", action_type="execute", payload={"intent": "pause_app", "target": display_name}, style="secondary"),
                            ]
                        elif runtime_status in ("stopped", "not_running") or static_status in ("active", "installed"):
                            actions = [
                                ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": display_name}, style="primary"),
                            ]
                        elif runtime_status == "paused":
                            actions = [
                                ActionSuggestion(id="resume", label="▶️ 恢复", action_type="execute", payload={"intent": "resume_app", "target": display_name}, style="primary"),
                            ]
                        if self._app_presenter:
                            return self._app_presenter.build_status_card_response(
                                session_id=session_id,
                                related_app=display_name,
                                icon=icon,
                                label=label,
                                actions=actions,
                            )
                        else:
                            return ChatMessageResponse(
                                type="card",
                                content=f"{icon} **{display_name}**：{label}",
                                session_id=session_id,
                                related_app=display_name,
                                actions=actions,
                            )
                except Exception as e:
                    logger.warning("App status resolution failed: %s", e)

            if self._app_command_service:
                return self._app_command_service.build_degraded_response(
                    intent="query_status",
                    session_id=session_id,
                    related_app=display_name,
                    reason="查询状态失败",
                    detail="请稍后重试。",
                )

            return ChatMessageResponse(
                type="text",
                content=f"📊 **{display_name}** 当前未运行。",
                session_id=session_id,
                related_app=display_name,
            )

        running = len([a for a in apps if a.get("status") == "running"])
        total = len(apps)
        if self._app_presenter:
            return self._app_presenter.build_system_status_response(
                session_id=session_id,
                total=total,
                running=running,
            )
        return ChatMessageResponse(
            type="text",
            content=f"📊 系统状态：共 {total} 个 App，其中 {running} 个运行中。",
            session_id=session_id,
        )

    async def _handle_query_help(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        return ChatMessageResponse(
            type="text",
            content="💠 光脑使用帮助\n\n"
                    "你可以用自然语言跟我对话，我能帮你：\n\n"
                    "📱 **App 管理**\n"
                    '• "帮我建一个 XX App" — 创建新 App\n'
                    '• "看看我的 App" — 查看 App 列表\n'
                    '• "启动/停止 XX" — 控制 App 运行\n'
                    '• "看看 XX 的状态" — 查询 App 详情\n\n'
                    "⚙️ **系统操作**\n"
                    '• "系统状态" — 查看整体状态\n'
                    '• "帮助" — 查看本帮助\n\n'
                    "💡 **提示**：说不清楚的时候，我会问你更多细节。",
            session_id=session_id,
            actions=[
                ActionSuggestion(id="list_apps", label="📱 查看 App", action_type="navigate", payload={"intent": "list_apps"}, style="primary"),
                ActionSuggestion(id="create_app", label="➕ 创建 App", action_type="navigate", payload={"intent": "create_app"}, style="secondary"),
            ],
        )

    async def _handle_modify_interactive_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        """Handle user request to modify the Interactive App UI."""
        user_request = command.raw_input or command.clarification_question or "优化界面"

        try:
            if hasattr(self, "_interactive_app_workflow") and self._interactive_app_workflow:
                result = self._interactive_app_workflow.modify_app(
                    user_id=command.user_id or "web-user",
                    user_request=user_request,
                    auto_activate=True,
                    require_confirmation=False,
                )
                return ChatMessageResponse(
                    type="card",
                    content=f"✅ 界面已更新！\n\n"
                            f"修改内容: {user_request}\n"
                            f"新版本: {result['new_version']}\n"
                            f"修改文件: {', '.join(result['files_changed'])}\n\n"
                            f"请刷新页面查看新界面。",
                    session_id=session_id,
                    actions=[
                        ActionSuggestion(id="query_status", label="📊 系统状态", action_type="execute", payload={"intent": "query_status"}, style="secondary"),
                    ],
                )
            else:
                return ChatMessageResponse(
                    type="text",
                    content="⚠️ 交互式 App 修改工作流未加载，无法执行自修改。",
                    session_id=session_id,
                    requires_input=False,
                )
        except Exception as e:
            return ChatMessageResponse(
                type="text",
                content=f"❌ 修改失败: {str(e)}\n\n请稍后重试。",
                session_id=session_id,
                requires_input=False,
            )

    def _resolve_instance_id(self, user_input: str) -> str:
        if not self._lifecycle or not hasattr(self._lifecycle, "list_instances"):
            return user_input
        try:
            self._lifecycle.get_instance(user_input)
            return user_input
        except Exception:
            pass
        normalized = user_input.replace("_", "-")
        if normalized != user_input:
            try:
                self._lifecycle.get_instance(normalized)
                return normalized
            except Exception:
                pass
        normalized2 = user_input.replace("-", "_")
        if normalized2 != user_input:
            try:
                self._lifecycle.get_instance(normalized2)
                return normalized2
            except Exception:
                pass
        try:
            for inst in self._lifecycle.list_instances():
                inst_id = getattr(inst, "id", "")
                if user_input.lower() in inst_id.lower() or inst_id.lower() in user_input.lower():
                    return inst_id
        except Exception:
            pass
        return user_input

    @staticmethod
    def _resolve_display_name(instance_id: str, blueprint_id: str) -> str:
        name = instance_id
        if ":" in name:
            name = name.split(":")[0]
        for prefix in ("bp.", "app.", "bp-"):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        name = name.replace("-", "_")
        return name

    def _error_reply(self, session_id: str, message: str) -> ChatMessageResponse:
        return ChatMessageResponse(
            type="error",
            content=message,
            session_id=session_id,
            requires_input=False,
        )

    async def _handle_permission(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if not self._permission_skill:
            return self._error_reply(session_id, "⚠️ 权限管理模块未加载。")
        user_id = command.user_id or ""
        if not user_id:
            return self._error_reply(session_id, "⚠️ 无法识别用户身份。")
        from app.services.system_skills.permission import parse_permission_command
        cmd = parse_permission_command(command.raw_input or "", user_id)
        if not cmd:
            return ChatMessageResponse(
                type="text",
                content="我没理解你的权限管理指令。试试说：\n• 列出所有用户\n• 查看我的权限\n• 给 xxx 管理员权限\n• 撤销 xxx 的管理员权限",
                session_id=session_id,
                requires_input=True,
            )
        result = self._permission_skill.execute(cmd, user_id)
        if result.get("success"):
            return ChatMessageResponse(
                type="text",
                content=result.get("message", "操作成功"),
                session_id=session_id,
                requires_input=False,
            )
        else:
            return self._error_reply(session_id, result.get("message", "操作失败"))

    async def _handle_runtime_asset_tool(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if not self._asset_tool_executor:
            return self._error_reply(session_id, "⚠️ 运行态资产工具模块未加载。")
        caller_id = f"user.{command.user_id}" if command.user_id else "system"
        payload = dict(command.parameters or {})
        if command.intent in {"query_asset_info", "query_asset_detail"} and not payload.get("asset_id") and command.target_app:
            payload["asset_id"] = command.target_app
        result = self._asset_tool_executor.execute(command.intent, payload, caller_id)
        if not result.success:
            return self._error_reply(session_id, f"❌ {result.error}")
        return ChatMessageResponse(
            type="text",
            content=json.dumps(result.data, ensure_ascii=False, indent=2),
            session_id=session_id,
            requires_input=False,
        )

    async def _handle_query_asset_detail(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        caller_id = f"user.{command.user_id}" if command.user_id else "system"
        asset_id = command.parameters.get("asset_id") or command.target_app
        if not asset_id:
            return ChatMessageResponse(
                type="text",
                content="请告诉我你想了解哪个资产的详细使用说明？",
                session_id=session_id,
                requires_input=True,
            )
        if self._asset_tool_executor:
            result = self._asset_tool_executor.execute(
                "query_asset_detail",
                {"asset_id": asset_id},
                caller_id,
            )
            if result.success:
                data = result.data
                interfaces = data.get("interfaces") or data.get("methods") or {}
                if isinstance(interfaces, list):
                    normalized_interfaces = {}
                    for item in interfaces:
                        if isinstance(item, dict):
                            key = item.get("name") or item.get("method") or "unknown"
                            normalized_interfaces[key] = item
                    interfaces = normalized_interfaces
                interface_lines = []
                for key, info in interfaces.items():
                    info = info or {}
                    desc = info.get("description", "")
                    input_schema = info.get("input_schema") or info.get("input") or {}
                    output_schema = info.get("output_schema") or info.get("output") or {}
                    line = f"\n**{key}** - {desc}" if desc else f"\n**{key}**"
                    if input_schema:
                        line += f"\n  输入: {json.dumps(input_schema, ensure_ascii=False)}"
                    if output_schema:
                        line += f"\n  输出: {json.dumps(output_schema, ensure_ascii=False)}"
                    interface_lines.append(line)
                if interface_lines:
                    content = (
                        f"📋 **{data.get('name', asset_id)}** 详细使用说明\n\n"
                        f"资产ID: {data.get('asset_id', asset_id)}\n"
                        f"{data.get('description', '')}\n\n"
                        f"**可用接口：**{''.join(interface_lines)}"
                    )
                else:
                    content = (
                        f"📋 **{data.get('name', asset_id)}** 详细使用说明\n\n"
                        f"资产ID: {data.get('asset_id', asset_id)}\n"
                        f"{data.get('description', '')}\n\n无可用接口"
                    )
                return ChatMessageResponse(
                    type="text",
                    content=content,
                    session_id=session_id,
                    requires_input=False,
                )
            else:
                return ChatMessageResponse(
                    type="text",
                    content=f"❌ 未找到资产「{asset_id}」或你没有权限查看。",
                    session_id=session_id,
                    requires_input=False,
                )
        return self._error_reply(session_id, "⚠️ 资产查询模块未加载。")

    def _handle_package_list_installed(self, command, session_id, apps):
        if not self._package_manager_executor:
            return self._error_reply(session_id, "⚠️ 包管理模块未加载。")
        result = self._package_manager_executor.execute("package_list_installed", command.parameters)
        if result.success:
            packages = result.data.get("packages", [])
            if not packages:
                return ChatMessageResponse(
                    type="text",
                    content="📦 当前没有已安装的包。\n\n可用 package_search 搜索可安装的包。",
                    session_id=session_id,
                    requires_input=False,
                )
            lines = ["📦 **已安装的包：**\n"]
            for p in packages:
                lines.append(f"- {p['asset_id']} ({p['asset_type']}) v{p['installed_version']}")
                if p.get('description'):
                    lines.append(f"  {p['description']}")
            return ChatMessageResponse(
                type="text",
                content="\n".join(lines),
                session_id=session_id,
                requires_input=False,
            )
        return self._error_reply(session_id, f"❌ 查询失败: {result.error}")

    def _handle_package_show(self, command, session_id, apps):
        if not self._package_manager_executor:
            return self._error_reply(session_id, "⚠️ 包管理模块未加载。")
        result = self._package_manager_executor.execute("package_show", command.parameters)
        if result.success:
            d = result.data
            lines = [f"📋 **{d.get('name', d['asset_id'])}**\n"]
            lines.append(f"类型: {d.get('asset_type', 'unknown')}")
            if d.get('source_version'):
                lines.append(f"源码版本: {d['source_version']}")
            if d.get('installed_version'):
                lines.append(f"已安装版本: {d['installed_version']}")
            if d.get('description'):
                lines.append(f"描述: {d['description']}")
            history = d.get('build_history', [])
            if history:
                lines.append(f"\n构建历史 ({len(history)} 次):")
                for h in history:
                    lines.append(f"  - v{h['version']} hash={h['build_hash'][:8]} ({h['build_time'][:16]})")
            return ChatMessageResponse(
                type="text",
                content="\n".join(lines),
                session_id=session_id,
                requires_input=False,
            )
        return self._error_reply(session_id, f"❌ {result.error}")

    def _handle_package_build(self, command, session_id, apps):
        if not self._package_manager_executor:
            return self._error_reply(session_id, "⚠️ 包管理模块未加载。")
        result = self._package_manager_executor.execute("package_build", command.parameters)
        if result.success:
            d = result.data
            return ChatMessageResponse(
                type="text",
                content=f"✅ 构建成功\n\n包: {d['asset_id']}\n版本: {d['version']}\nHash: {d['build_hash']}\n时间: {d['build_time']}",
                session_id=session_id,
                requires_input=False,
            )
        return self._error_reply(session_id, f"❌ 构建失败: {result.error}")

    def _handle_package_install(self, command, session_id, apps):
        if not self._package_manager_executor:
            return self._error_reply(session_id, "⚠️ 包管理模块未加载。")
        result = self._package_manager_executor.execute("package_install", command.parameters)
        if result.success:
            d = result.data
            msg = f"✅ 安装成功\n\n包: {d['asset_id']}\n版本: {d['installed_version']}"
            if d.get('build_hash'):
                msg += f"\nHash: {d['build_hash']}"
            return ChatMessageResponse(
                type="text",
                content=msg,
                session_id=session_id,
                requires_input=False,
            )
        return self._error_reply(session_id, f"❌ 安装失败: {result.error}")

    def _handle_package_uninstall(self, command, session_id, apps):
        if not self._package_manager_executor:
            return self._error_reply(session_id, "⚠️ 包管理模块未加载。")
        result = self._package_manager_executor.execute("package_uninstall", command.parameters)
        if result.success:
            return ChatMessageResponse(
                type="text",
                content=f"✅ 已卸载: {command.parameters.get('asset_id', 'unknown')}",
                session_id=session_id,
                requires_input=False,
            )
        return self._error_reply(session_id, f"❌ 卸载失败: {result.error}")

    def _handle_package_rollback(self, command, session_id, apps):
        if not self._package_manager_executor:
            return self._error_reply(session_id, "⚠️ 包管理模块未加载。")
        result = self._package_manager_executor.execute("package_rollback", command.parameters)
        if result.success:
            d = result.data
            return ChatMessageResponse(
                type="text",
                content=f"✅ 回滚成功\n\n包: {d['asset_id']}\n回滚到: v{d['rolled_back_to']}",
                session_id=session_id,
                requires_input=False,
            )
        return self._error_reply(session_id, f"❌ 回滚失败: {result.error}")

    def _handle_package_search(self, command, session_id, apps):
        if not self._package_manager_executor:
            return self._error_reply(session_id, "⚠️ 包管理模块未加载。")
        result = self._package_manager_executor.execute("package_search", command.parameters)
        if result.success:
            packages = result.data.get("packages", [])
            if not packages:
                return ChatMessageResponse(
                    type="text",
                    content=f"🔍 未找到与 '{command.parameters.get('query', '')}' 匹配的包。",
                    session_id=session_id,
                    requires_input=False,
                )
            lines = [f"🔍 搜索结果（{len(packages)} 个）:\n"]
            for p in packages:
                status = "✅ 已安装" if p.get("installed") else "❌ 未安装"
                lines.append(f"- {p['asset_id']} ({p['asset_type']}) v{p['version']} [{status}]")
                if p.get('description'):
                    lines.append(f"  {p['description']}")
            return ChatMessageResponse(
                type="text",
                content="\n".join(lines),
                session_id=session_id,
                requires_input=False,
            )
        return self._error_reply(session_id, f"❌ 搜索失败: {result.error}")

    def _handle_master_execute(self, command, session_id, apps):
        if not self._master_control:
            return self._error_reply(session_id, "⚠️ 主控模块未加载。")
        operation = command.parameters.get("operation") or command.intent
        user_id = command.user_id or "system"
        target = command.parameters.get("target", "")
        user_role = "user"
        if self._permission_skill and hasattr(self._permission_skill, "get_user_role"):
            try:
                user_role = self._permission_skill.get_user_role(user_id)
            except Exception:
                pass
        params = {k: v for k, v in command.parameters.items() if k != "operation"}
        import asyncio
        result = self._master_control.execute(
            operation=operation,
            user_id=user_id,
            user_role=user_role,
            target=target,
            params=params,
        )
        if asyncio.iscoroutine(result):
            try:
                result = asyncio.get_event_loop().run_until_complete(result)
            except RuntimeError:
                pass
        if isinstance(result, dict):
            status = result.get("status", "unknown")
            message = result.get("message", "")
            data = result.get("data")
            if status == "denied":
                required = result.get("required_role", "")
                return ChatMessageResponse(
                    type="text",
                    content=f"❌ 权限不足: {message}" + (f"\n需要 {required} 角色。" if required else ""),
                    session_id=session_id,
                    requires_input=False,
                )
            elif status == "success":
                content = f"✅ {message or '操作成功'}"
                if data:
                    content += f"\n\n{json.dumps(data, ensure_ascii=False, indent=2)}"
                return ChatMessageResponse(
                    type="text",
                    content=content,
                    session_id=session_id,
                    requires_input=False,
                )
            elif status == "delegated":
                return ChatMessageResponse(
                    type="text",
                    content=f"ℹ️ {message}",
                    session_id=session_id,
                    requires_input=False,
                )
            else:
                return self._error_reply(session_id, f"❌ {message or f'操作失败: {status}'}")
        return self._error_reply(session_id, "⚠️ 主控返回了意外结果。")

    async def _handle_list_apps(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        """Handle list_apps intent — show available apps."""
        if not apps:
            return ChatMessageResponse(
                type="text",
                content="📱 你还没有任何 App。\n\n对我说「帮我建一个监控 App」来创建你的第一个应用。",
                session_id=session_id,
                actions=[
                    ActionSuggestion(id="create_app", label="➕ 创建 App", action_type="navigate", payload={"intent": "create_app"}, style="primary"),
                ],
            )
        lines = ["📱 你的 App 列表：\n"]
        for app in apps:
            status = app.get("status", "unknown")
            name = app.get("display_name") or app.get("name") or app.get("id", "未知")
            icon = {"running": "🟢", "paused": "🟡", "stopped": "🔴"}.get(status, "⚪")
            lines.append(f"{icon} {name} ({status})")
        return ChatMessageResponse(
            type="list",
            content="\n".join(lines),
            session_id=session_id,
        )

    async def _handle_cancel(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        """Handle cancel intent — acknowledge cancellation."""
        return ChatMessageResponse(
            type="text",
            content="✅ 已取消当前操作。",
            session_id=session_id,
        )

    def _auto_save(self) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.save_state(
                lifecycle=self._lifecycle,
                light_brain_memory=self._memory,
            )
        except Exception as e:
            logger.warning("Failed to auto-save state: %s", e)

    # Backward compatibility: session management delegated to memory
    def list_sessions(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """List sessions for a user (or all if user_id is None)."""
        if not self._memory:
            return []
        return self._memory.list_sessions(user_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID."""
        if not self._memory:
            return False
        return self._memory.delete_session(session_id)

    async def execute_action(
        self,
        user_id: str,
        session_id: str,
        action_id: str,
        action_params: dict[str, Any] | None = None,
    ) -> ChatMessageResponse:
        """Execute an action from a previous reply (button click)."""
        action_params = action_params or {}
        intent = action_params.get("intent", "unclear")
        target = action_params.get("target", "")

        from app.models.chat import InterpretedCommand

        command = InterpretedCommand(
            intent=intent,
            confidence=1.0 if intent != "unclear" else 0.0,
            target_app=(action_params.get("target_app") or target or None),
            parameters=dict(action_params.get("parameters") or {}),
            user_id=user_id,
            raw_input=f"action:{action_id}",
        )
        command = self._enrich_command(command, session_id, [])
        self._memory.record_command(session_id, command)
        result = await self._execute_command(command, session_id, [])
        self._memory.record_reply(session_id, result)
        self._auto_save()
        return result
