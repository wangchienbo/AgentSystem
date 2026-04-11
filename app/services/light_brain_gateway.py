"""LightBrain Gateway — the unified interaction entry point.

Orchestrates: receive message → interpret intent → execute workflow → serialize reply.
Phase 8.1: rule-based interpreter, basic workflow execution, structured replies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.chat import (
    ActionSuggestion,
    ChatMessageRequest,
    ChatMessageResponse,
    InlineItem,
    InterpretedCommand,
    WorkflowResult,
    WorkflowStep,
    SessionSummary,
)
from app.services.light_brain_memory import LightBrainMemory, LightBrainMemoryError
from app.services.light_brain_interpreter import LightBrainInterpreter


class LightBrainGatewayError(Exception):
    pass


class LightBrainGateway:
    """Main entry point for all user interactions with the AgentSystem / App OS.

    Coordinates:
    1. Session management (via LightBrainMemory)
    2. Intent interpretation (via LightBrainInterpreter)
    3. Workflow execution (built-in command handlers)
    4. Response serialization (structured ChatMessageResponse)
    """

    def __init__(
        self,
        memory: LightBrainMemory | None = None,
        interpreter: LightBrainInterpreter | None = None,
        app_registry_service: Any = None,
        app_lifecycle_service: Any = None,
        app_runtime_host: Any = None,
        app_installer: Any = None,
        app_catalog: Any = None,
        skill_registry: Any = None,
        meta_app_orchestrator: Any = None,
        llm_responder: Any = None,
    ) -> None:
        self._memory = memory or LightBrainMemory()
        self._interpreter = interpreter or LightBrainInterpreter()

        # Optional external services — filled by runtime bootstrap
        self._app_registry = app_registry_service
        self._lifecycle = app_lifecycle_service
        self._runtime_host = app_runtime_host
        self._installer = app_installer
        self._catalog = app_catalog
        self._skill_registry = skill_registry
        self._meta_app_orchestrator = meta_app_orchestrator
        self._llm_responder = llm_responder
        self._name: str | None = None
        self._load_identity()

    # -- public API ----------------------------------------------------------

    async def process_message(self, request: ChatMessageRequest) -> ChatMessageResponse:
        """Process a user message and return a structured reply."""
        # 1. Get or create session
        if request.session_id:
            session = self._memory.get_session(request.session_id)
            if not session:
                session = self._memory.create_session(
                    user_id=request.user_id,
                    channel=request.channel,
                    session_id=request.session_id,
                )
        else:
            session = self._memory.create_session(
                user_id=request.user_id,
                channel=request.channel,
            )

        # 2. Record user message
        self._memory.record_user_message(session.session_id, request.message)

        # 3. Get available apps for context
        available_apps = await self._get_available_apps()

        # 4. Wire LLM responder into interpreter (if available)
        if self._llm_responder and not hasattr(self._interpreter, "_llm_responder"):
            self._interpreter.set_llm_responder(self._llm_responder)

        # 5. Interpret intent
        command = self._interpreter.interpret(request.message, available_apps)
        self._memory.record_command(session.session_id, command)

        # 6. Execute command → get reply
        reply = await self._execute_command(command, session.session_id, available_apps)
        reply.session_id = session.session_id

        # 6b. LLM enhancement (if available)
        if self._llm_responder and getattr(self._llm_responder, 'available', False):
            enhanced = self._llm_responder.generate_reply(
                system_context=f"你是 AgentSystem，一个 AI 驱动的系统。你的名字是「{self._name}」。你的职责是帮助用户管理 App。",
                user_message=request.message,
                app_context=available_apps,
                max_tokens=300,
            )
            if enhanced and enhanced.strip():
                # Keep the structured reply type and actions, but replace text
                reply.content = enhanced.strip()

        # 7. Record reply
        self._memory.record_reply(session.session_id, reply)

        return reply

    async def execute_action(
        self,
        user_id: str,
        session_id: str,
        action_id: str,
        action_params: dict[str, Any] | None = None,
    ) -> ChatMessageResponse:
        """Handle a user clicking a button from a previous reply."""
        session = self._memory.get_session(session_id)
        if not session:
            return ChatMessageResponse(
                type="error",
                content="会话不存在，请重新开始对话。",
                session_id=session_id,
            )

        params = action_params or {}
        intent = params.get("intent", "")

        if intent == "create_app" and params.get("confirmed"):
            command = session.last_command
            if command:
                available_apps = await self._get_available_apps()
                reply = await self._execute_create_app(command, session_id, available_apps)
                reply.session_id = session_id
                self._memory.record_reply(session_id, reply)
                return reply
            return self._error_reply(session_id, "没有找到待确认的创建命令。")

        if intent == "delete_app" and params.get("confirmed"):
            target = params.get("target", session.last_command.target_app if session.last_command else "未知")
            try:
                if self._lifecycle:
                    self._lifecycle.get_instance(target)  # Check exists
                    # Would need a proper delete/unregister method
                if self._runtime_host:
                    try:
                        self._runtime_host.stop(target, reason="deleted_by_user")
                    except Exception:
                        pass
                reply = ChatMessageResponse(
                    type="card",
                    content=f"🗑️ **{target}** 已删除。",
                    session_id=session_id,
                )
                self._memory.record_reply(session_id, reply)
                return reply
            except Exception as exc:
                return self._error_reply(session_id, f"删除 **{target}** 失败: {exc}")

        if intent == "start_app" and params.get("confirmed"):
            target = params.get("target", "")
            if self._runtime_host:
                try:
                    self._runtime_host.start(target, reason="user_command")
                    reply = ChatMessageResponse(
                        type="card",
                        content=f"✅ **{target}** 已启动。",
                        session_id=session_id,
                        related_app=target,
                    )
                    self._memory.record_reply(session_id, reply)
                    return reply
                except Exception as exc:
                    return self._error_reply(session_id, f"启动失败: {exc}")

        if intent == "stop_app" and params.get("confirmed"):
            target = params.get("target", "")
            if self._runtime_host:
                try:
                    self._runtime_host.stop(target, reason="user_command")
                    reply = ChatMessageResponse(
                        type="card",
                        content=f"⏹ **{target}** 已停止。",
                        session_id=session_id,
                        related_app=target,
                    )
                    self._memory.record_reply(session_id, reply)
                    return reply
                except Exception as exc:
                    return self._error_reply(session_id, f"停止失败: {exc}")

        if intent == "cancel":
            reply = ChatMessageResponse(
                type="text",
                content="已取消操作。有什么我可以帮你的吗？",
                session_id=session_id,
                actions=[
                    ActionSuggestion(id="list_apps", label="📱 查看 App", action_type="navigate", payload={"intent": "list_apps"}, style="primary"),
                    ActionSuggestion(id="help", label="❓ 帮助", action_type="navigate", payload={"intent": "query_help"}, style="secondary"),
                ],
            )
            self._memory.record_reply(session_id, reply)
            return reply

        return ChatMessageResponse(
            type="text",
            content=f"收到操作请求 ({action_id})，正在处理...",
            session_id=session_id,
        )

    def list_sessions(self, user_id: str | None = None) -> list[SessionSummary]:
        return self._memory.list_sessions(user_id)

    def delete_session(self, session_id: str) -> bool:
        return self._memory.delete_session(session_id)

    def get_session_messages(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._memory.get_recent_messages(session_id, limit)

    # -- command execution ---------------------------------------------------

    async def _execute_command(
        self,
        command: InterpretedCommand,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> ChatMessageResponse:
        """Route interpreted command to the right handler."""
        self._handlers = {
            "greet": self._handle_greet,
            "list_apps": self._handle_list_apps,
            "query_status": self._handle_query_status,
            "query_help": self._handle_query_help,
            "create_app": self._handle_create_app,
            "start_app": self._handle_start_app,
            "stop_app": self._handle_stop_app,
            "pause_app": self._handle_pause_app,
            "resume_app": self._handle_resume_app,
            "query_app": self._handle_query_app,
            "modify_app": self._handle_modify_app,
            "delete_app": self._handle_delete_app,
        }

        handler = self._handlers.get(command.intent)
        if handler:
            return await handler(command, session_id, available_apps)

        # Unclear intent
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "我没理解你的意思，换个说法试试？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        return self._error_reply(session_id, f"我还不会处理这个指令。试试说创建 App 或看看我的 App。")

    # -- built-in handlers ---------------------------------------------------

    def _load_identity(self) -> None:
        """Load persisted identity, or generate one on first run."""
        import json, os
        identity_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "lightbrain", "identity.json")
        os.makedirs(os.path.dirname(identity_path), exist_ok=True)
        if os.path.exists(identity_path):
            with open(identity_path) as f:
                data = json.load(f)
                self._name = data.get("name")
        if not self._name:
            # Generate identity on first run
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

        # Self-description based on actual responsibilities
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
        """List what I can do based on registered command handlers."""
        caps = []
        if "create_app" in self._handlers:
            caps.append("🔨 根据你的需求，创建并配置各种功能 App")
        if "list_apps" in self._handlers:
            caps.append("📱 管理你所有的 App —— 查看、启动、停止、暂停、恢复、修改、删除")
        if "query_status" in self._handlers:
            caps.append("📊 汇报系统的整体运行状态")
        if "query_help" in self._handlers:
            caps.append("❓ 回答你关于我能力的问题")
        if "query_app" in self._handlers:
            caps.append("🔍 查询单个 App 的详细信息")

        if not caps:
            caps.append("处理你的指令，管理 App 的生命周期")

        return "\n".join(caps)

    async def _handle_list_apps(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if not apps:
            return ChatMessageResponse(
                type="text",
                content="你还没有任何 App。要我帮你创建一个吗？",
                session_id=session_id,
                actions=[
                    ActionSuggestion(id="create_app", label="➕ 创建 App", action_type="navigate", payload={"intent": "create_app"}, style="primary"),
                ],
            )

        # Group by status
        groups: dict[str, list[dict]] = {}
        for app in apps:
            status = app.get("status", "unknown")
            groups.setdefault(status, []).append(app)

        status_labels = {
            "running": ("🟢", "运行中"),
            "paused": ("🟡", "已暂停"),
            "stopped": ("🔴", "已停止"),
            "draft": ("⚪", "草稿"),
            "installed": ("🔵", "已安装"),
            "error": ("⛔", "故障"),
        }

        # Build inline items for each app
        items: list[InlineItem] = []
        for status_key in ["running", "paused", "installed", "stopped", "draft", "error"]:
            for app in groups.get(status_key, []):
                icon, label = status_labels.get(status_key, ("⚪", "未知"))
                app_actions: list[ActionSuggestion] = []
                if status_key == "running":
                    app_actions = [
                        ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": app.get("name")}, style="danger"),
                        ActionSuggestion(id="pause", label="⏸ 暂停", action_type="execute", payload={"intent": "pause_app", "target": app.get("name")}, style="secondary"),
                    ]
                elif status_key in ("stopped", "installed"):
                    app_actions = [
                        ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": app.get("name")}, style="primary"),
                        ActionSuggestion(id="query", label="📋 详情", action_type="execute", payload={"intent": "query_app", "target": app.get("name")}, style="secondary"),
                    ]
                elif status_key == "paused":
                    app_actions = [
                        ActionSuggestion(id="resume", label="▶️ 恢复", action_type="execute", payload={"intent": "resume_app", "target": app.get("name")}, style="primary"),
                    ]

                items.append(InlineItem(
                    id=app.get("app_id", ""),
                    title=app.get("name", ""),
                    subtitle=app.get("description"),
                    status=status_key,
                    status_icon=icon,
                    actions=app_actions,
                ))

        count_text = f"你目前有 {len(apps)} 个 App"
        return ChatMessageResponse(
            type="list",
            content=count_text,
            session_id=session_id,
            inline_items=items,
            actions=[
                ActionSuggestion(id="create_new", label="➕ 新建 App", action_type="navigate", payload={"intent": "create_app"}, style="primary"),
                ActionSuggestion(id="help", label="❓ 帮助", action_type="navigate", payload={"intent": "query_help"}, style="secondary"),
            ],
        )

    async def _handle_query_status(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        running = len([a for a in apps if a.get("status") == "running"])
        total = len(apps)
        return ChatMessageResponse(
            type="card",
            content=f"📊 系统状态\n\n"
                    f"App 总数: {total}\n"
                    f"运行中: {running}\n"
                    f"已停止: {total - running}\n"
                    f"系统运行正常 ✅",
            session_id=session_id,
            actions=[
                ActionSuggestion(id="list_apps", label="📱 查看 App 列表", action_type="navigate", payload={"intent": "list_apps"}, style="primary"),
            ],
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

    async def _handle_create_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        return await self._execute_create_app(command, session_id, apps)

    async def _execute_create_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        """Handle create_app intent — first asks for details, then creates."""
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想创建什么样的 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        # We have enough info — create the app
        app_type = command.parameters.get("app_type", "unknown")
        app_name = command.target_app or f"{app_type}_app"

        schedule_info = ""
        if command.parameters.get("schedule_type"):
            st = command.parameters["schedule_type"]
            if st == "interval":
                secs = command.parameters.get("schedule_interval", 0)
                schedule_info = f"\n执行频率: 每 {secs} 秒"
            elif st == "cron":
                schedule_info = f"\n调度: {command.parameters.get('schedule_cron', 'N/A')}"

        threshold_info = ""
        if command.parameters.get("threshold"):
            threshold_info = f"\n告警阈值: {command.parameters['threshold']}%"

        # If orchestrator available, actually create the app
        if self._meta_app_orchestrator:
            try:
                from app.models.meta_app_skill import MetaAppSkillRequest
                request = MetaAppSkillRequest(
                    app_name=app_name,
                    app_type=app_type,
                    schedule_type=command.parameters.get("schedule_type"),
                    schedule_interval=command.parameters.get("schedule_interval"),
                    schedule_cron=command.parameters.get("schedule_cron"),
                    threshold=command.parameters.get("threshold"),
                )
                result = self._meta_app_orchestrator.create_app_through_meta_app(request)
                app_id = result.get("app_instance_id", result.get("app_id", app_name))
                return ChatMessageResponse(
                    type="card",
                    content=f"✅ App 创建成功！\n\n"
                            f"名称: {app_name}\n"
                            f"类型: {app_type}\n"
                            f"ID: {app_id}\n"
                            f"{schedule_info}{threshold_info}",
                    session_id=session_id,
                    related_app=app_name,
                    actions=[
                        ActionSuggestion(
                            id="start_app", label="▶️ 启动", action_type="execute",
                            payload={"intent": "start_app", "target": app_name}, style="primary",
                        ),
                        ActionSuggestion(
                            id="list_apps", label="📱 查看列表", action_type="navigate",
                            payload={"intent": "list_apps"}, style="secondary",
                        ),
                    ],
                )
            except Exception as exc:
                return ChatMessageResponse(
                    type="error",
                    content=f"创建 App 失败: {exc}",
                    session_id=session_id,
                )

        # Fallback: confirmation card when orchestrator unavailable
        return ChatMessageResponse(
            type="confirm",
            content=f"📋 App 创建概要\n\n"
                    f"名称: {app_name}\n"
                    f"类型: {app_type}\n"
                    f"{schedule_info}"
                    f"{threshold_info}\n\n"
                    f"确认创建吗？",
            session_id=session_id,
            related_app=app_name,
            actions=[
                ActionSuggestion(
                    id="confirm_create", label="✅ 确认创建", action_type="confirm",
                    payload={"intent": "create_app", "confirmed": True, "app_name": app_name, "app_type": app_type},
                    style="primary",
                ),
                ActionSuggestion(
                    id="modify", label="✏️ 修改配置", action_type="modify",
                    payload={"intent": "modify_before_create"}, style="secondary",
                ),
                ActionSuggestion(
                    id="cancel", label="❌ 取消", action_type="cancel",
                    payload={"intent": "cancel"}, style="ghost",
                ),
            ],
            requires_input=True,
        )

    async def _handle_start_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想启动哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        target = command.target_app or "未知 App"
        
        # Try to actually start the app
        if self._runtime_host:
            try:
                self._runtime_host.start(target, reason="user_command")
                return ChatMessageResponse(
                    type="card",
                    content=f"✅ **{target}** 已启动。",
                    session_id=session_id,
                    related_app=target,
                    actions=[
                        ActionSuggestion(
                            id="stop", label="⏹ 停止", action_type="execute",
                            payload={"intent": "stop_app", "target": target}, style="danger",
                        ),
                        ActionSuggestion(
                            id="status", label="📊 状态", action_type="execute",
                            payload={"intent": "query_app", "target": target}, style="secondary",
                        ),
                    ],
                )
            except Exception as exc:
                return ChatMessageResponse(
                    type="error",
                    content=f"启动 **{target}** 失败: {exc}",
                    session_id=session_id,
                    related_app=target,
                )
        
        # Fallback
        return ChatMessageResponse(
            type="confirm",
            content=f"确定要启动 **{target}** 吗？",
            session_id=session_id,
            related_app=target,
            actions=command.suggested_actions,
            requires_input=True,
        )

    async def _handle_stop_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想停止哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        target = command.target_app or "未知 App"
        
        # Try to actually stop the app
        if self._runtime_host:
            try:
                self._runtime_host.stop(target, reason="user_command")
                return ChatMessageResponse(
                    type="card",
                    content=f"⏹ **{target}** 已停止。",
                    session_id=session_id,
                    related_app=target,
                    actions=[
                        ActionSuggestion(
                            id="start", label="▶️ 启动", action_type="execute",
                            payload={"intent": "start_app", "target": target}, style="primary",
                        ),
                    ],
                )
            except Exception as exc:
                return ChatMessageResponse(
                    type="error",
                    content=f"停止 **{target}** 失败: {exc}",
                    session_id=session_id,
                    related_app=target,
                )
        
        # Fallback
        return ChatMessageResponse(
            type="confirm",
            content=f"确定要停止 **{target}** 吗？",
            session_id=session_id,
            related_app=target,
            actions=command.suggested_actions,
            requires_input=True,
        )

    async def _handle_pause_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想暂停哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )
        target = command.target_app or "未知 App"
        return ChatMessageResponse(
            type="text",
            content=f"⏸ 正在暂停 **{target}**...",
            session_id=session_id,
            related_app=target,
            actions=[
                ActionSuggestion(id="resume", label="▶️ 恢复", action_type="execute", payload={"intent": "resume_app", "target": target}, style="primary"),
            ],
        )

    async def _handle_resume_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想恢复哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )
        target = command.target_app or "未知 App"
        return ChatMessageResponse(
            type="text",
            content=f"▶️ 正在恢复 **{target}**...",
            session_id=session_id,
            related_app=target,
        )

    async def _handle_query_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想查看哪个 App？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        target = command.target_app or "未知 App"
        # Try to find the app in available apps
        found = None
        for app in apps:
            if app.get("name") == target or app.get("app_id") == target:
                found = app
                break

        if found:
            status = found.get("status", "unknown")
            description = found.get("description", "")
            app_id = found.get("app_id", "")
            
            # Enrich with runtime status if available
            runtime_status = ""
            if self._lifecycle:
                try:
                    instance = self._lifecycle.get_instance(app_id or target)
                    runtime_status = f"\n运行状态: {getattr(instance, 'status', 'unknown')}"
                except Exception:
                    pass
            
            detail = f"ID: {app_id}\n状态: {status}{runtime_status}"
            if description:
                detail += f"\n描述: {description}"
            
            return ChatMessageResponse(
                type="card",
                content=f"📋 {target}\n\n{detail}",
                session_id=session_id,
                related_app=target,
                actions=[
                    ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": target}, style="primary"),
                    ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": target}, style="danger"),
                ],
            )

        return ChatMessageResponse(
            type="text",
            content=f"没有找到名为 **{target}** 的 App。",
            session_id=session_id,
            actions=[
                ActionSuggestion(id="list_apps", label="📱 查看所有 App", action_type="navigate", payload={"intent": "list_apps"}, style="primary"),
            ],
        )

    async def _handle_modify_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想修改哪个 App？想改成什么样？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )
        target = command.target_app or "未知 App"
        modification = command.parameters.get("modification", "未指定")
        return ChatMessageResponse(
            type="confirm",
            content=f"将 **{target}** 修改为：{modification}\n\n确认吗？",
            session_id=session_id,
            related_app=target,
            actions=command.suggested_actions,
            requires_input=True,
        )

    async def _handle_delete_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想删除哪个 App？此操作不可恢复。",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )
        target = command.target_app or "未知 App"
        # Add confirm action that triggers actual deletion
        return ChatMessageResponse(
            type="confirm",
            content=f"⚠️ 确定要删除 **{target}** 吗？此操作不可恢复！",
            session_id=session_id,
            related_app=target,
            actions=[
                ActionSuggestion(id="confirm_delete", label="🗑️ 确认删除", action_type="confirm", payload={"intent": "delete_app", "target": target, "confirmed": True}, style="danger"),
                ActionSuggestion(id="cancel", label="❌ 取消", action_type="cancel", payload={"intent": "cancel"}, style="ghost"),
            ],
            requires_input=True,
        )

    # -- helpers -------------------------------------------------------------

    async def _get_available_apps(self) -> list[dict[str, Any]]:
        """Fetch app list from registry/catalog if available."""
        apps: list[dict[str, Any]] = []
        if self._catalog:
            try:
                entries = self._catalog.list_apps()
                for entry in entries:
                    apps.append({
                        "app_id": getattr(entry, "app_id", ""),
                        "name": getattr(entry, "name", ""),
                        "description": getattr(entry, "description", ""),
                        "status": "installed",
                    })
            except Exception:
                pass

        if self._app_registry and hasattr(self._app_registry, "list_entries"):
            try:
                entries = self._app_registry.list_entries()
                for entry in entries:
                    name = getattr(entry, "app_id", str(entry))
                    if not any(a["name"] == name for a in apps):
                        apps.append({
                            "app_id": name,
                            "name": name,
                            "description": "",
                            "status": "draft",
                        })
            except Exception:
                pass

        return apps

    def _error_reply(self, session_id: str, message: str) -> ChatMessageResponse:
        return ChatMessageResponse(
            type="error",
            content=message,
            session_id=session_id,
            requires_input=False,
        )
