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
from app.services.tool_registry import ToolRegistry


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
        app_design_orchestrator: Any = None,
        llm_responder: Any = None,
        persistence_service: Any = None,
        interactive_app: Any = None,
        interactive_app_workflow: Any = None,
        permission_skill: Any = None,
        tool_registry: Any = None,
        orchestrator_bridge: Any = None,
        app_refinement_orchestrator: Any = None,
        # Asset registry & tool call chain
        system_catalog: Any = None,
        asset_tool_executor: Any = None,
        user_service: Any = None,
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
        self._app_design_orchestrator = app_design_orchestrator
        self._llm_responder = llm_responder
        self._persistence = persistence_service
        self._interactive_app = interactive_app
        self._interactive_app_workflow = interactive_app_workflow
        self._permission_skill = permission_skill
        self._tool_registry = tool_registry
        if self._tool_registry is None:
            self._tool_registry = self._build_default_tool_registry()
        self._name: str | None = None
        self._load_identity()

        # G.1/G.2: Orchestrator bridge — new execution chain
        self._orchestrator_bridge = orchestrator_bridge
        self._app_refinement_orchestrator = app_refinement_orchestrator

        # Asset registry & tool call chain
        self._system_catalog = system_catalog
        self._asset_tool_executor = asset_tool_executor
        self._user_service = user_service

        # Phase F.4: Multi-turn state — track active skill per session
        self._active_skills: dict[str, dict[str, Any]] = {}

    # -- multi-turn state management (Phase F.4) ----------------------------

    def _get_active_skill(self, session_id: str) -> dict[str, Any] | None:
        """Get the active skill context for a session, if any."""
        return self._active_skills.get(session_id)

    def _set_active_skill(self, session_id: str, skill_id: str, state: dict[str, Any] | None = None) -> None:
        """Mark a skill as active for a session (waiting for user input)."""
        self._active_skills[session_id] = {
            "skill_id": skill_id,
            "state": state or {},
            "set_at": datetime.now(UTC).isoformat(),
        }

    def _clear_active_skill(self, session_id: str) -> None:
        """Clear the active skill context for a session."""
        self._active_skills.pop(session_id, None)

    def get_active_skills(self) -> dict[str, dict[str, Any]]:
        """Return a snapshot of all active skill states (for debugging/inspection)."""
        return dict(self._active_skills)

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

        # 3. Phase F.4: Check for active skill (multi-turn continuation)
        active = self._get_active_skill(session.session_id)
        if active:
            # Continue the active skill conversation
            reply = await self._handle_active_skill_continuation(
                session.session_id, request.message, active,
            )
            reply.session_id = session.session_id
            self._memory.record_reply(session.session_id, reply)
            self._auto_save()
            return reply

        # 4. Ensure user exists (self-registration)
        if self._user_service and request.user_id:
            try:
                self._user_service.ensure_user(request.user_id)
            except Exception:
                pass  # Best-effort

        # 5. Get available apps for context
        available_apps = await self._get_available_apps(user_id=request.user_id)

        # 5b. Wire system_catalog into interpreter for asset-aware LLM parsing
        if self._system_catalog and not hasattr(self._interpreter, "_system_catalog"):
            self._interpreter.set_system_catalog(self._system_catalog)

        # 6. Wire LLM responder into interpreter (if available)
        if self._llm_responder and not hasattr(self._interpreter, "_llm_responder"):
            self._interpreter.set_llm_responder(self._llm_responder)

        # 7. Interpret intent
        command = self._interpreter.interpret(request.message, available_apps, user_id=request.user_id)
        command.user_id = request.user_id
        command.raw_input = request.message
        self._memory.record_command(session.session_id, command)

        # 7. Execute command → get reply
        reply = await self._execute_command(command, session.session_id, available_apps)
        reply.session_id = session.session_id

        # 7b. Phase F.4: Track active skill state based on reply
        if reply.requires_input:
            # The handler is waiting for user follow-up — track it
            self._set_active_skill(session.session_id, command.intent or "unknown", {
                "parameters": command.parameters,
                "target_app": command.target_app,
            })
        else:
            # Interaction complete, clear any prior active state
            self._clear_active_skill(session.session_id)

        # 6b. LLM enhancement (if available) — skip for permission/structured commands
        _LLM_SKIP_INTENTS = {"grant_admin", "grant_root", "revoke_role", "show_permissions", "list_users", "show_self", "query_status", "list_apps", "greet", "query_help"}
        if self._llm_responder and getattr(self._llm_responder, 'available', False) and command.intent not in _LLM_SKIP_INTENTS:
            # Build system context with memory and preferences
            system_ctx = f"你是 AgentSystem，一个 AI 驱动的系统。你的名字是「{self._name}」。你的职责是帮助用户管理 App。"

            # Inject user interaction preferences
            if request.user_id:
                try:
                    from app.services.system_skills.memory import MemorySkillService
                    mem_svc = MemorySkillService()
                    profile = mem_svc.get_profile(request.user_id)
                    if profile and profile.preferences:
                        prefs = profile.preferences
                        parts = []
                        style = prefs.get('style', [])
                        if style:
                            parts.append(f"回复风格：{', '.join(style)}")
                        lang = prefs.get('language')
                        if lang:
                            parts.append(f"回复语言：{lang}")
                        custom = prefs.get('custom_instructions')
                        if custom:
                            parts.append(f"自定义指令：\n{custom}")
                        tags = prefs.get('custom_tags', [])
                        if tags:
                            parts.append(f"用户偏好标签：{', '.join(tags)}")
                        if parts:
                            system_ctx += "\n\n用户交互偏好设置：\n" + "\n".join(parts)
                except Exception:
                    pass  # Silently ignore preference load failures

            if request.memory_context:
                system_ctx += f"\n\n用户记忆上下文：{request.memory_context}"
            enhanced, usage = self._llm_responder.generate_reply(
                system_context=system_ctx,
                user_message=request.message,
                app_context=available_apps,
                tool_registry=self._tool_registry,
                executed_tool=command.intent if command.intent not in _LLM_SKIP_INTENTS else None,
                max_tokens=300,
            )
            if enhanced and enhanced.strip():
                # Keep the structured reply type and actions, but replace text
                reply.content = enhanced.strip()
                # Attach usage info if we got it
                if usage:
                    reply.usage = usage

        # 7. Record reply
        self._memory.record_reply(session.session_id, reply)

        # 8. Persist state after each message
        self._auto_save()

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
            # Rebuild command from action_params if last_command is lost (e.g., page refresh)
            command = session.last_command
            if not command and params.get("app_name"):
                command = InterpretedCommand(
                    intent="create_app",
                    target_app=params["app_name"],
                    parameters=params.get("parameters", {"app_type": params.get("app_type", "unknown")}),
                    requires_clarification=False,
                )
            if command:
                available_apps = await self._get_available_apps(user_id=command.user_id)
                reply = await self._execute_create_app(command, session_id, available_apps)
                reply.session_id = session_id
                self._memory.record_reply(session_id, reply)
                return reply
            return ChatMessageResponse(
                type="error",
                content="没有找到待确认的创建命令。请重新发送创建请求。",
                session_id=session_id,
            )

        if intent == "delete_app" and params.get("confirmed"):
            target_input = params.get("target", session.last_command.target_app if session.last_command else "未知")
            target = self._resolve_instance_id(target_input)
            display_name = self._resolve_display_name(target, "")
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
                    content=f"🗑️ **{display_name}** 已删除。",
                    session_id=session_id,
                )
                self._memory.record_reply(session_id, reply)
                return reply
            except Exception as exc:
                return self._error_reply(session_id, f"删除 **{display_name}** 失败: {exc}")

        if intent == "start_app" and params.get("confirmed"):
            target_input = params.get("target", "")
            target = self._resolve_instance_id(target_input)
            display_name = self._resolve_display_name(target, "")
            if self._runtime_host:
                try:
                    self._runtime_host.start(target, reason="user_command")
                    reply = ChatMessageResponse(
                        type="card",
                        content=f"✅ **{display_name}** 已启动。",
                        session_id=session_id,
                        related_app=display_name,
                    )
                    self._memory.record_reply(session_id, reply)
                    return reply
                except Exception as exc:
                    return self._error_reply(session_id, f"启动失败: {exc}")

        if intent == "stop_app" and params.get("confirmed"):
            target_input = params.get("target", "")
            target = self._resolve_instance_id(target_input)
            display_name = self._resolve_display_name(target, "")
            if self._runtime_host:
                try:
                    self._runtime_host.stop(target, reason="user_command")
                    reply = ChatMessageResponse(
                        type="card",
                        content=f"⏹ **{display_name}** 已停止。",
                        session_id=session_id,
                        related_app=display_name,
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

    def get_last_session(self, user_id: str) -> _SessionRecord | None:
        """Get the most recently active session for a user."""
        user_sessions = [
            s for s in self._memory._sessions.values()
            if s.user_id == user_id and s.messages
        ]
        if not user_sessions:
            return None
        return max(user_sessions, key=lambda s: s.last_active_at)

    def list_sessions(self, user_id: str | None = None) -> list[SessionSummary]:
        return self._memory.list_sessions(user_id)

    def delete_session(self, session_id: str) -> bool:
        return self._memory.delete_session(session_id)

    def get_session_messages(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._memory.get_recent_messages(session_id, limit)

    def get_token_usage(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate token usage statistics across sessions."""
        sessions = self._memory.list_sessions(user_id)
        total_prompt = 0
        total_completion = 0
        total_tokens = 0
        total_calls = 0
        cached_calls = 0
        per_session: list[dict] = []

        for summary in sessions:
            if session_id and summary.session_id != session_id:
                continue
            record = self._memory.get_session(summary.session_id)
            if not record:
                continue

            session_prompt = 0
            session_completion = 0
            session_tokens = 0
            session_calls = 0
            session_cached = 0

            # Scan messages for usage data
            for msg in record.messages:
                if msg.get("role") != "assistant":
                    continue
                usage = msg.get("usage")
                if usage:
                    session_prompt += usage.get("prompt_tokens", 0)
                    session_completion += usage.get("completion_tokens", 0)
                    session_tokens += usage.get("total_tokens", 0)
                    session_calls += 1
                    if usage.get("cached"):
                        session_cached += 1

            total_prompt += session_prompt
            total_completion += session_completion
            total_tokens += session_tokens
            total_calls += session_calls
            cached_calls += session_cached

            if session_calls > 0:
                per_session.append({
                    "session_id": summary.session_id,
                    "prompt_tokens": session_prompt,
                    "completion_tokens": session_completion,
                    "total_tokens": session_tokens,
                    "llm_calls": session_calls,
                    "cached_calls": session_cached,
                })

        return {
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "total_llm_calls": total_calls,
            "cached_calls": cached_calls,
            "sessions": per_session,
        }

    # -- multi-turn active skill continuation (Phase F.4) -------------------

    async def _handle_active_skill_continuation(
        self,
        session_id: str,
        user_message: str,
        active: dict[str, Any],
    ) -> ChatMessageResponse:
        """Handle a user message when there's an active skill waiting for input.

        This implements Phase F.4 multi-turn state management: instead of
        re-interpreting the intent, route directly to the active skill.
        """
        skill_id = active.get("skill_id", "unknown")
        state = active.get("state", {})

        # Route based on which skill is active
        if skill_id == "create_app" or skill_id == "app_creator":
            # User is providing details for app creation
            command = InterpretedCommand(
                intent="create_app",
                target_app=state.get("target_app", ""),
                parameters={**state.get("parameters", {}), "follow_up": user_message},
                requires_clarification=False,
            )
            available_apps = await self._get_available_apps(user_id=command.user_id)
            reply = await self._execute_create_app(command, session_id, available_apps)
            # If this reply still requires input, keep the active state
            if reply.requires_input:
                self._set_active_skill(session_id, "create_app", state)
            else:
                self._clear_active_skill(session_id)
            return reply

        elif skill_id in ("start_app", "stop_app", "pause_app", "resume_app", "delete_app", "modify_app", "query_app"):
            # User clarified which app to act on
            command = InterpretedCommand(
                intent=skill_id,
                target_app=user_message.strip(),
                parameters={"from_active_skill": True},
                requires_clarification=False,
            )
            available_apps = await self._get_available_apps(user_id=command.user_id)
            reply = await self._execute_command(command, session_id, available_apps)
            if reply.requires_input:
                self._set_active_skill(session_id, skill_id, state)
            else:
                self._clear_active_skill(session_id)
            return reply

        else:
            # Unknown active skill — clear and fall through to normal intent
            self._clear_active_skill(session_id)
            available_apps = await self._get_available_apps(user_id=command.user_id)
            command = self._interpreter.interpret(user_message, available_apps)
            command.raw_input = user_message
            self._memory.record_command(session_id, command)
            reply = await self._execute_command(command, session_id, available_apps)
            if reply.requires_input:
                self._set_active_skill(session_id, command.intent or "unknown", {})
            return reply

    # -- command execution ---------------------------------------------------

    async def _execute_command(
        self,
        command: InterpretedCommand,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> ChatMessageResponse:
        """Route interpreted command to the right handler.

        G.1/G.2: Try the new orchestrator bridge first; if it returns
        a result use it, otherwise fall back to the legacy handler chain.
        """
        # ── Local-only intents: skip bridge (avoids RPC timeout) ──────
        _BRIDGE_SKIP_INTENTS = {"query_status", "list_apps", "greet", "query_help", "start_app", "stop_app", "pause_app", "resume_app", "query_app"}

        # ── G.1/G.2: Try new chain first ──────────────────────────────
        if (self._orchestrator_bridge
                and self._orchestrator_bridge.is_available()
                and command.intent not in _BRIDGE_SKIP_INTENTS):
            try:
                bridge_result = await self._orchestrator_bridge.execute_command(
                    user_id=command.user_id or "",
                    app_instance_id="default",
                    text=command.raw_input or "",
                    session_id=session_id,
                )
                if bridge_result is not None:
                    # Bridge handled it — convert to ChatMessageResponse
                    return ChatMessageResponse(
                        type=bridge_result.get("type", "text"),
                        content=bridge_result.get("content", ""),
                        session_id=session_id,
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Bridge execution failed, falling back to legacy: %s", e,
                )
            # bridge_result was None → fall through to legacy

        # ── Legacy handler chain (backward compatible) ────────────────
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
            "modify_interactive_app": self._handle_modify_interactive_app,
            "self_modify": self._handle_modify_interactive_app,
            "grant_admin": self._handle_permission,
            "grant_root": self._handle_permission,
            "revoke_role": self._handle_permission,
            "show_permissions": self._handle_permission,
            "list_users": self._handle_permission,
            "show_self": self._handle_permission,
            "query_asset_detail": self._handle_query_asset_detail,
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


    def _build_default_tool_registry(self):
        """Initialize default tool registry with built-in handler descriptions."""
        from app.services.tool_registry import ToolRegistry, ToolDefinition, ToolParameter
        registry = ToolRegistry()

        # App lifecycle tools
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

        # App management tools
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

        # Permission tools
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

        # System tools
        registry.register(ToolDefinition(
            name="query_status",
            description="查询系统整体运行状态。用户说'系统状态'、'运行情况'时使用。",
            parameters=[],
            category="system", priority=7,
        ))

        return registry

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
        # Show apps owned by the user + system-wide apps (owner="system" or empty)
        user_id = command.user_id or ""
        user_apps = []
        for app in apps:
            owner = app.get("owner_user_id", "")
            if owner == user_id or owner == "system" or not owner:
                user_apps.append(app)
        
        # If user has no apps at all, show empty state
        if not user_apps:
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
        for app in user_apps:
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

        count_text = f"你目前有 {len(user_apps)} 个 App"
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
        # If user asks about a specific app, show its status
        if command.target_app:
            target = self._resolve_instance_id(command.target_app)
            display_name = self._resolve_display_name(target, command.target_app)
            found = None
            for app in apps:
                if app.get("name") == display_name or app.get("app_id") == target:
                    found = app
                    break
            if found:
                status = found.get("status", "unknown")
                status_icons = {"running": "🟢", "paused": "🟡", "stopped": "🔴", "installed": "🔵", "error": "⛔"}
                icon = status_icons.get(status, "⚪")
                status_labels = {"running": "运行中", "paused": "已暂停", "stopped": "已停止", "installed": "已安装", "error": "故障"}
                label = status_labels.get(status, status)
                actions = []
                if status == "running":
                    actions = [
                        ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": display_name}, style="danger"),
                        ActionSuggestion(id="pause", label="⏸ 暂停", action_type="execute", payload={"intent": "pause_app", "target": display_name}, style="secondary"),
                    ]
                elif status in ("stopped", "installed"):
                    actions = [
                        ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": display_name}, style="primary"),
                    ]
                elif status == "paused":
                    actions = [
                        ActionSuggestion(id="resume", label="▶️ 恢复", action_type="execute", payload={"intent": "resume_app", "target": display_name}, style="primary"),
                    ]
                return ChatMessageResponse(
                    type="card",
                    content=f"{icon} **{display_name}**\n\n状态: {label}",
                    session_id=session_id,
                    related_app=display_name,
                    actions=actions,
                )
            return ChatMessageResponse(
                type="text",
                content=f"未找到 App：**{command.target_app}**",
                session_id=session_id,
            )

        # No target — show system-wide status
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
        # Use extracted Chinese display name if available, otherwise fallback
        app_name = command.target_app or command.parameters.get("app_name_display") or f"{app_type}_app"

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
                from app.models.app_meta_app import AppCreationFromMetaAppRequest
                user_id = command.user_id or ""
                request = AppCreationFromMetaAppRequest(
                    app_name=app_name,
                    goal=f"创建一个{app_type}类型的 App：{app_name}",
                    app_kind="service",
                    complexity="moderate",
                    scope={"app_type": app_type},
                    context=f"用户请求创建一个{app_type}应用",
                    user_id=user_id,
                )
                result = self._meta_app_orchestrator.create_app_through_meta_app(request)
                # Handle both dict and object results
                if hasattr(result, 'error') and result.error:
                    return ChatMessageResponse(
                        type="error",
                        content=f"创建 App 失败: {result.error}",
                        session_id=session_id,
                    )

                # -- Permission check: regular user creating app with new skills --
                user_id = command.user_id or "web-user"
                new_skill_ids = getattr(result, 'created_skill_ids', []) or []
                if new_skill_ids:
                    perm = self._check_app_modify_permission(user_id, app_name)
                    if not perm["can_create_skills"]:
                        return ChatMessageResponse(
                            type="text",
                            content=(
                                f"⚠️ 创建 **{app_name}** 需要以下新 skill：\n"
                                f"`{', '.join(new_skill_ids)}`\n\n"
                                f"**Skill 是系统共有资产**，只有 **管理员及以上** 用户才能创建。\n\n"
                                f"请联系管理员来帮你创建这些 skill，或者用已有 skill 重新组合一个 App。"
                            ),
                            session_id=session_id,
                            related_app=app_name,
                        )
                app_id = ""
                if result.installed_app:
                    app_id = result.installed_app.id
                elif hasattr(result, 'control_plan') and result.control_plan:
                    app_id = result.control_plan.app_slug
                if not app_id:
                    app_id = app_name
                # Persist state so the app survives server restarts
                if self._persistence:
                    try:
                        self._persistence.save_state(
                            lifecycle=self._lifecycle,
                            runtime_host=self._runtime_host,
                            registry=self._app_registry,
                            catalog=self._catalog,
                        )
                    except Exception:
                        pass  # Best-effort persistence
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
                    payload={"intent": "create_app", "confirmed": True, "app_name": app_name, "app_type": app_type,
                             "parameters": command.parameters},
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

        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        
        # Try to actually start the app
        if self._runtime_host:
            try:
                self._runtime_host.start(target, reason="user_command")
                display_name = self._resolve_display_name(target, "")
                return ChatMessageResponse(
                    type="card",
                    content=f"✅ **{display_name}** 已启动。",
                    session_id=session_id,
                    related_app=display_name,
                    actions=[
                        ActionSuggestion(
                            id="stop", label="⏹ 停止", action_type="execute",
                            payload={"intent": "stop_app", "target": display_name}, style="danger",
                        ),
                        ActionSuggestion(
                            id="status", label="📊 状态", action_type="execute",
                            payload={"intent": "query_app", "target": display_name}, style="secondary",
                        ),
                    ],
                )
            except Exception as exc:
                exc_str = str(exc)
                # User-friendly error messages
                if "Invalid lifecycle transition" in exc_str or "running -> running" in exc_str:
                    display_name = self._resolve_display_name(target, target_input)
                    return ChatMessageResponse(
                        type="text",
                        content=f"**{display_name}** 已经在运行中，不需要重复启动。",
                        session_id=session_id,
                        related_app=display_name,
                    )
                if "not found" in exc_str.lower() or "No instance" in exc_str:
                    return ChatMessageResponse(
                        type="text",
                        content=f"未找到 App：**{target_input}**，请先创建它。",
                        session_id=session_id,
                    )
                return ChatMessageResponse(
                    type="error",
                    content=f"启动 **{target_input}** 失败: {exc}",
                    session_id=session_id,
                    related_app=target_input,
                )
        
        # Fallback
        return ChatMessageResponse(
            type="confirm",
            content=f"确定要启动 **{target_input}** 吗？",
            session_id=session_id,
            related_app=target_input,
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

        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        
        # Try to actually stop the app
        if self._runtime_host:
            try:
                self._runtime_host.stop(target, reason="user_command")
                display_name = self._resolve_display_name(target, "")
                return ChatMessageResponse(
                    type="card",
                    content=f"⏹ **{display_name}** 已停止。",
                    session_id=session_id,
                    related_app=display_name,
                    actions=[
                        ActionSuggestion(
                            id="start", label="▶️ 启动", action_type="execute",
                            payload={"intent": "start_app", "target": display_name}, style="primary",
                        ),
                    ],
                )
            except Exception as exc:
                exc_str = str(exc)
                # User-friendly error messages
                if "Invalid lifecycle transition" in exc_str or "stopped -> stopped" in exc_str:
                    display_name = self._resolve_display_name(target, target_input)
                    return ChatMessageResponse(
                        type="text",
                        content=f"**{display_name}** 已经处于停止状态。",
                        session_id=session_id,
                        related_app=display_name,
                    )
                if "not found" in exc_str.lower() or "No instance" in exc_str:
                    return ChatMessageResponse(
                        type="text",
                        content=f"未找到 App：**{target_input}**，请先创建它。",
                        session_id=session_id,
                    )
                return ChatMessageResponse(
                    type="error",
                    content=f"停止 **{target_input}** 失败: {exc}",
                    session_id=session_id,
                    related_app=target_input,
                )
        
        # Fallback
        return ChatMessageResponse(
            type="confirm",
            content=f"确定要停止 **{target_input}** 吗？",
            session_id=session_id,
            related_app=target_input,
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
        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        # Try to actually pause the app
        if self._lifecycle:
            try:
                instance = self._lifecycle.get_instance(target)
                current_status = getattr(instance, 'status', 'unknown') if instance else 'unknown'
                if current_status == 'paused':
                    return ChatMessageResponse(
                        type="text",
                        content=f"**{display_name}** 已经处于暂停状态。",
                        session_id=session_id,
                        related_app=display_name,
                    )
                self._lifecycle.pause(target, reason="user_command")
                return ChatMessageResponse(
                    type="text",
                    content=f"⏸ **{display_name}** 已暂停。",
                    session_id=session_id,
                    related_app=display_name,
                    actions=[
                        ActionSuggestion(id="resume", label="▶️ 恢复", action_type="execute", payload={"intent": "resume_app", "target": display_name}, style="primary"),
                        ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": display_name}, style="secondary"),
                    ],
                )
            except Exception as exc:
                exc_str = str(exc)
                if "Invalid lifecycle transition" in exc_str or "stopped -> paused" in exc_str:
                    return ChatMessageResponse(
                        type="text",
                        content=f"**{display_name}** 当前已停止，无法暂停。请先启动后再暂停。",
                        session_id=session_id,
                        related_app=display_name,
                    )

        return ChatMessageResponse(
            type="text",
            content=f"⏸ **{display_name}** 已暂停。",
            session_id=session_id,
            related_app=display_name,
            actions=[
                ActionSuggestion(id="resume", label="▶️ 恢复", action_type="execute", payload={"intent": "resume_app", "target": display_name}, style="primary"),
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
        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        # Try to actually resume the app
        if self._lifecycle:
            try:
                instance = self._lifecycle.get_instance(target)
                current_status = getattr(instance, 'status', 'unknown') if instance else 'unknown'
                if current_status == 'running':
                    return ChatMessageResponse(
                        type="text",
                        content=f"**{display_name}** 已经在运行中。",
                        session_id=session_id,
                        related_app=display_name,
                    )
                if current_status != 'paused':
                    return ChatMessageResponse(
                        type="text",
                        content=f"**{display_name}** 当前处于{current_status}状态，请先暂停后再恢复。",
                        session_id=session_id,
                        related_app=display_name,
                    )
                self._lifecycle.resume(target, reason="user_command")
            except Exception as exc:
                pass  # Best-effort resume

        return ChatMessageResponse(
            type="text",
            content=f"▶️ **{display_name}** 已恢复运行。",
            session_id=session_id,
            related_app=display_name,
            actions=[
                ActionSuggestion(id="pause", label="⏸ 暂停", action_type="execute", payload={"intent": "pause_app", "target": display_name}, style="secondary"),
                ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": display_name}, style="danger"),
            ],
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

        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        # Try to find the app in available apps
        found = None
        for app in apps:
            if app.get("name") == display_name or app.get("app_id") == target:
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
                    instance = self._lifecycle.get_instance(target)
                    runtime_status = f"\n运行状态: {getattr(instance, 'status', 'unknown')}"
                except Exception:
                    pass
            
            detail = f"ID: {app_id}\n状态: {status}{runtime_status}"
            if description:
                detail += f"\n描述: {description}"
            
            return ChatMessageResponse(
                type="card",
                content=f"📋 {display_name}\n\n{detail}",
                session_id=session_id,
                related_app=display_name,
                actions=[
                    ActionSuggestion(id="start", label="▶️ 启动", action_type="execute", payload={"intent": "start_app", "target": display_name}, style="primary"),
                    ActionSuggestion(id="stop", label="⏹ 停止", action_type="execute", payload={"intent": "stop_app", "target": display_name}, style="danger"),
                ],
            )

        return ChatMessageResponse(
            type="text",
            content=f"没有找到名为 **{target_input}** 的 App。",
            session_id=session_id,
            actions=[
                ActionSuggestion(id="list_apps", label="📱 查看所有 App", action_type="navigate", payload={"intent": "list_apps"}, style="primary"),
            ],
        )

    async def _handle_modify_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        # Phase 1: clarification needed
        if command.requires_clarification:
            return ChatMessageResponse(
                type="text",
                content=command.clarification_question or "你想修改哪个 App？想改成什么样？",
                session_id=session_id,
                actions=command.suggested_actions,
                requires_input=True,
            )

        # Phase 2: user confirmed the modification (via action button with confirmed=True)
        params = command.parameters or {}
        if params.get("confirmed"):
            return await self._execute_modify_app(command, session_id, apps)

        # Phase 1b: show confirmation dialog with proper action buttons
        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        modification = params.get("modification", "未指定")
        return ChatMessageResponse(
            type="confirm",
            content=(
                f"将 **{display_name}** 修改为：{modification}\n\n"
                f"确认后系统会分析需求，使用已有 skill 或生成新 skill 来完成修改。\n\n"
                f"⚠️ 注意：如果修改需要生成新 skill，仅管理员及以上用户可执行。"
            ),
            session_id=session_id,
            related_app=display_name,
            actions=[
                ActionSuggestion(
                    id="confirm_modify",
                    label="✅ 确认修改",
                    action_type="confirm",
                    payload={
                        "intent": "modify_app",
                        "target_app": target,
                        "modification": modification,
                        "confirmed": True,
                    },
                    style="primary",
                ),
                ActionSuggestion(
                    id="cancel",
                    label="❌ 取消",
                    action_type="cancel",
                    payload={"intent": "cancel"},
                    style="ghost",
                ),
            ],
            requires_input=True,
        )

    async def _execute_modify_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        """Execute the actual App modification via the refinement orchestrator.

        Permission model:
        - Skill = shared asset, only admin+ can create/modify skills
        - App = user asset, belongs to whoever created it
        - To modify an App: user's role level must be >= app owner's role level
        - If modification requires new skills: only admin+ can proceed
        """
        params = command.parameters or {}
        target_input = params.get("target_app", command.target_app) or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        modification = params.get("modification", "未指定")
        user_id = command.user_id or "web-user"

        # -- Step 1: Permission check — can this user modify the app? --
        perm_result = self._check_app_modify_permission(user_id, target)
        if not perm_result["allowed"]:
            return ChatMessageResponse(
                type="text",
                content=perm_result["message"],
                session_id=session_id,
                related_app=display_name,
            )
        can_create_skills = perm_result["can_create_skills"]

        if not self._app_refinement_orchestrator:
            return ChatMessageResponse(
                type="text",
                content=f"⚠️ App 修改功能尚未完全启用（refinement orchestrator 未注入）。\n\n你的需求已记录：**{display_name}** 需要 **{modification}**\n请在下次系统更新后重试。",
                session_id=session_id,
                related_app=display_name,
            )

        try:
            from app.models.app_refinement import SuggestedSkillRefinementClosureRequest

            # -- Step 2: Dry-run analysis — what skills are needed? --
            dry_request = SuggestedSkillRefinementClosureRequest(
                blueprint_id=target,
                name=display_name,
                goal=f"修改 {display_name}：{modification}",
                user_id=user_id,
                install=False,  # Dry run: don't install yet
                run=False,
                trigger="manual",
                reviewer=user_id,
                version="dry-run",
                note=f"权限检查：{modification}",
            )
            dry_result = self._app_refinement_orchestrator.refine_closure(dry_request)

            # Dry-run stores would-create skills in diagnostics (safe, no side effects)
            would_create = [d for d in (dry_result.diagnostics or []) if d.get("status") == "would_create"]
            skill_names = [d["skill_id"] for d in would_create]
            reused = dry_result.reused_skill_ids or []
            needs_new_skills = len(skill_names) > 0

            # -- Step 3: If new skills needed but user can't create → block before any creation --
            if needs_new_skills and not can_create_skills:
                return ChatMessageResponse(
                    type="text",
                    content=(
                        f"⚠️ **{display_name}** 的修改需要以下新 skill：\n"
                        f"`{', '.join(skill_names)}`\n\n"
                        f"**Skill 是系统共有资产**，只有 **管理员及以上** 用户才能创建。\n\n"
                        f"请联系管理员来帮你创建这些 skill，或者使用已有 skill 重新组合一个 App。"
                    ),
                    session_id=session_id,
                    related_app=display_name,
                )

            # -- Step 4: Permission passed — execute the real modification --
            if needs_new_skills:
                # Admin creating new skills — proceed with full execution
                request = SuggestedSkillRefinementClosureRequest(
                    blueprint_id=target,
                    name=display_name,
                    goal=f"修改 {display_name}：{modification}",
                    user_id=user_id,
                    install=True,
                    run=False,
                    trigger="manual",
                    reviewer=user_id,
                    version="modified-1",
                    note=f"用户修改：{modification}",
                )
                result = self._app_refinement_orchestrator.refine_closure(request)
            else:
                # Only reusing existing skills — use dry_result as the result
                result = dry_result

            # -- Step 3: Success --
            summary_parts = [f"✅ **{display_name}** 修改完成！"]
            if skill_names:
                summary_parts.append(f"🆕 新生成 skill：{', '.join(skill_names)}")
            if reused:
                summary_parts.append(f"♻️ 复用已有 skill：{', '.join(reused)}")
            summary_parts.append(f"\n修改内容：{modification}")

            if result.diagnostics:
                warnings = [d.get("message", "未知问题") for d in result.diagnostics]
                summary_parts.append(f"\n⚠️ 注意：{'；'.join(warnings)}")

            return ChatMessageResponse(
                type="text",
                content="\n".join(summary_parts),
                session_id=session_id,
                related_app=display_name,
                actions=[
                    ActionSuggestion(
                        id="list_apps", label="📱 查看 App", action_type="navigate",
                        payload={"intent": "list_apps"}, style="secondary",
                    ),
                ],
            )

        except Exception as e:
            return ChatMessageResponse(
                type="text",
                content=f"❌ 修改 **{display_name}** 时出错：{e}\n\n请重试或联系系统管理员。",
                session_id=session_id,
                related_app=display_name,
            )

    # ===========================================================================
    # Permission helpers for App modification
    # ===========================================================================

    _ROLE_LEVEL = {"user": 0, "admin": 1, "root": 2}

    def _check_app_modify_permission(self, user_id: str, app_id: str) -> dict:
        """Check if user can modify an App.

        Returns dict with:
        - allowed: bool
        - can_create_skills: bool (admin+ only)
        - message: str (reason if denied)
        """
        try:
            from app.services.user_service import Role, UserService
            user_svc = self._get_user_service()
            if not user_svc:
                # No user service = allow (fallback for single-user mode)
                return {"allowed": True, "can_create_skills": True, "message": ""}

            user = user_svc.get_user(user_id)
            if not user:
                return {"allowed": False, "can_create_skills": False,
                        "message": f"⚠️ 用户 '{user_id}' 未注册，无法执行修改操作。"}

            user_level = self._ROLE_LEVEL.get(user.role, 0)
            is_admin = user.is_admin

            # Find app owner role
            app_owner_role = self._get_app_owner_role(app_id)
            app_level = self._ROLE_LEVEL.get(app_owner_role, 0)

            if user_level < app_level:
                return {
                    "allowed": False, "can_create_skills": False,
                    "message": (
                        f"⚠️ 你没有权限修改 **{app_id}**。\n\n"
                        f"该 App 的创建者权限级别为 **{app_owner_role}**，\n"
                        f"只有权限 ≥ {app_owner_role} 的用户才能修改它。\n"
                        f"你的角色: {user.role}"
                    ),
                }

            return {"allowed": True, "can_create_skills": is_admin, "message": ""}

        except Exception as e:
            return {"allowed": False, "can_create_skills": False,
                    "message": f"⚠️ 权限检查失败：{e}"}

    def _get_user_service(self):
        """Get UserService from available services."""
        if hasattr(self, "_permission_skill") and self._permission_skill:
            return getattr(self._permission_skill, "_user_service", None)
        return None

    def _get_app_owner_role(self, app_id: str) -> str:
        """Get the owner role of an App."""
        try:
            if self._lifecycle:
                instance = self._lifecycle.get_instance(app_id)
                if instance and hasattr(instance, "owner_user_id"):
                    # Look up the owner's role
                    user_svc = self._get_user_service()
                    if user_svc:
                        owner = user_svc.get_user(instance.owner_user_id)
                        if owner:
                            return owner.role
        except Exception:
            pass
        # Fallback: check blueprint
        try:
            if self._app_registry:
                bp = self._app_registry.get_blueprint(app_id)
                if bp and hasattr(bp, "owner_role"):
                    return bp.owner_role
        except Exception:
            pass
        return "user"  # Default fallback

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
        target_input = command.target_app or "未知 App"
        target = self._resolve_instance_id(target_input)
        display_name = self._resolve_display_name(target, "")
        # Add confirm action that triggers actual deletion
        return ChatMessageResponse(
            type="confirm",
            content=f"⚠️ 确定要删除 **{display_name}** 吗？此操作不可恢复！",
            session_id=session_id,
            related_app=display_name,
            actions=[
                ActionSuggestion(id="confirm_delete", label="🗑️ 确认删除", action_type="confirm", payload={"intent": "delete_app", "target": target, "confirmed": True}, style="danger"),
                ActionSuggestion(id="cancel", label="❌ 取消", action_type="cancel", payload={"intent": "cancel"}, style="ghost"),
            ],
            requires_input=True,
        )

    async def _handle_modify_interactive_app(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        """Handle user request to modify the Interactive App UI."""
        user_request = command.raw_input or command.clarification_question or "优化界面"

        try:
            if hasattr(self, "_interactive_app_workflow") and self._interactive_app_workflow:
                # Execute self-modification workflow
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
                        ActionSuggestion(
                            id="refresh_page", label="🔄 刷新页面", action_type="navigate",
                            payload={"intent": "refresh", "url": "/"}, style="primary",
                        ),
                    ],
                    requires_input=False,
                )
            else:
                return ChatMessageResponse(
                    type="text",
                    content=f"🔧 自修改功能尚未完全启用。\n\n"
                            f"你的需求是：{user_request}\n"
                            f"我已记录这个需求，后续会实现。",
                    session_id=session_id,
                    requires_input=False,
                )
        except Exception as exc:
            return ChatMessageResponse(
                type="error",
                content=f"❌ 界面修改失败: {exc}",
                session_id=session_id,
            )

    # -- helpers -------------------------------------------------------------

    async def _get_available_apps(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch app list from lifecycle (primary source) + catalog/registry (supplemental).
        
        If user_id is provided, only return apps owned by that user.
        """
        apps: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # Primary: lifecycle instances (source of truth for runtime state)
        if self._lifecycle and hasattr(self._lifecycle, "list_instances"):
            try:
                for inst in self._lifecycle.list_instances():
                    app_id = getattr(inst, "id", "")
                    if app_id in seen_ids:
                        continue
                    inst_owner = getattr(inst, "owner_user_id", "")
                    # Filter by user_id if provided
                    if user_id and inst_owner and inst_owner != user_id:
                        continue
                    seen_ids.add(app_id)
                    name = self._resolve_display_name(app_id, getattr(inst, "blueprint_id", ""))
                    apps.append({
                        "app_id": app_id,
                        "name": name,
                        "description": "",
                        "status": getattr(inst, "status", "unknown"),
                        "blueprint_id": getattr(inst, "blueprint_id", ""),
                        "owner_user_id": inst_owner,
                    })
            except Exception:
                pass

        # Supplemental: catalog entries (pre-installed system apps)
        if self._catalog:
            try:
                entries = self._catalog.list_apps()
                for entry in entries:
                    app_id = getattr(entry, "app_id", "")
                    if app_id in seen_ids:
                        continue
                    seen_ids.add(app_id)
                    apps.append({
                        "app_id": app_id,
                        "name": getattr(entry, "name", app_id),
                        "description": getattr(entry, "description", ""),
                        "status": "installed",
                    })
            except Exception:
                pass

        # Supplemental: registry entries (blueprints without instances yet)
        if self._app_registry and hasattr(self._app_registry, "list_entries"):
            try:
                entries = self._app_registry.list_entries()
                for entry in entries:
                    name = getattr(entry, "app_id", str(entry))
                    if name in seen_ids:
                        continue
                    seen_ids.add(name)
                    apps.append({
                        "app_id": name,
                        "name": name,
                        "description": "",
                        "status": "draft",
                    })
            except Exception:
                pass

        return apps

    def _resolve_instance_id(self, user_input: str) -> str:
        """Resolve a user-provided app name to the actual instance ID.

        Handles cases where the user says 'translator_app' but the instance
        ID is 'translator-app', or vice versa.
        """
        if not self._lifecycle or not hasattr(self._lifecycle, "list_instances"):
            return user_input

        # Direct match
        try:
            self._lifecycle.get_instance(user_input)
            return user_input
        except Exception:
            pass

        # Normalize: try replacing _ with - and vice versa
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

        # Fuzzy: check if any instance ID contains the user input (minus common suffixes)
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
        """Derive a user-friendly display name from an instance ID."""
        name = instance_id
        # Handle colon-separated suffixes (e.g., "bp.usable.alpha:usable-alpha-user")
        if ":" in name:
            name = name.split(":")[0]
        # Strip common prefixes
        for prefix in ("bp.", "app.", "bp-"):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        # Convert hyphens to underscores for user-friendly display
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
        self,
        command: InterpretedCommand,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> ChatMessageResponse:
        """Handle permission management commands through the chat interface."""
        if not self._permission_skill:
            return self._error_reply(session_id, "⚠️ 权限管理模块未加载。")

        user_id = command.user_id or ""
        if not user_id:
            return self._error_reply(session_id, "⚠️ 无法识别用户身份。")

        # Import and use the permission skill parser
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

    async def _handle_query_asset_detail(
        self,
        command: InterpretedCommand,
        session_id: str,
        available_apps: list[dict[str, Any]],
    ) -> ChatMessageResponse:
        """Handle query_asset_detail tool call from LLM.
        
        This is called when the LLM decides it needs to look up detailed usage
        instructions for a specific asset.
        """
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
                interfaces = data.get("interfaces", {})
                interface_lines = []
                for key, info in interfaces.items():
                    desc = info.get("description", "")
                    input_schema = info.get("input_schema", {})
                    output_schema = info.get("output_schema", {})
                    line = f"\n**{key}** - {desc}"
                    if input_schema:
                        line += f"\n  输入: {json.dumps(input_schema, ensure_ascii=False)}"
                    if output_schema:
                        line += f"\n  输出: {json.dumps(output_schema, ensure_ascii=False)}"
                    interface_lines.append(line)
                
                content = (
                    f"📋 **{data.get('name', asset_id)}** 详细使用说明\n\n"
                    f"{data.get('description', '')}\n\n"
                    f"**可用接口：**"
                    + "\n".join(interface_lines) if interface_lines else "\n无可用接口"
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
                    content=f"❌ 找不到资产「{asset_id}」或你没有权限查看。",
                    session_id=session_id,
                    requires_input=False,
                )
        
        return self._error_reply(session_id, "⚠️ 资产查询模块未加载。")

    def _auto_save(self) -> None:
        """Auto-save state if persistence service is available."""
        if self._persistence is None:
            return
        try:
            self._persistence.save_state(
                lifecycle=self._lifecycle,
                runtime_host=self._runtime_host,
                registry=self._app_registry,
                catalog=self._catalog,
                light_brain_memory=self._memory,
            )
        except Exception:
            # Never let persistence failures break the interaction
            pass
