"""LightBrain Gateway — the unified interaction entry point.

Orchestrates: receive message → interpret intent → execute workflow → serialize reply.
Phase 8.1: rule-based interpreter, basic workflow execution, structured replies.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.models.chat import (
    ActionSuggestion,
    ChatMessageRequest,
    ChatMessageResponse,
    InlineItem,
    InterpretedCommand,
    TaskContinuationDecision,
)
from app.models.telemetry import InteractionTelemetryRecord
from app.services.context_center import ContextCenter
from app.models.context import SessionContextRecord, SessionLink, SessionNode
from app.models.pending_task import PendingTaskRecord
from app.services.light_brain_interpreter import LightBrainInterpreter
from app.services.tool_registry import ToolRegistry
from app.system.catalog.runtime_center import RuntimeCenter
from app.config.context_upload import (
    ContextUploadConfig,
    is_content_allowed_for_upload,
    format_system_note,
)
from app.utils.context_upload import ContextUploadHelper
from app.services.rate_limiter import RateLimiter, RateLimitConfig
from app.services.tool_loop_guard import ToolLoopGuard, ToolLoopConfig
from app.utils.observability import ObservabilityCollector
from app.utils.context_upload import ContextUploadHelper
from app.config.context_upload import ContextUploadConfig

from app.services.contract_linter import ContractLinter
from app.system.management_presenters import (
    render_app_list,
    render_management_availability,
    render_management_status,
    render_package_detail,
    render_package_list,
    render_package_operation_result,
)
from app.system.self_iteration_strategy_formatter import (
    render_self_iteration_asset_detail,
    render_self_iteration_asset_list,
    render_self_iteration_strategy_overview,
)
from app.system.runtime_asset_formatter import render_asset_detail_document, render_asset_info_summary

logger = logging.getLogger(__name__)


class LightBrainGateway:
    """Unified entry point: message → intent → execution → reply."""

    RUNTIME_ASSET_TOOL_INTENTS = {"call_asset_method"}

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
        context_center: ContextCenter | None = None,
        runtime_center: RuntimeCenter | None = None,
        **extra_deps,
    ):
        self._memory = memory
        self._interpreter = interpreter
        self._skill_runner = skill_runner
        self._lifecycle = lifecycle or app_lifecycle_service  # legacy alias
        self._log_center = log_center
        self._persistence = persistence or persistence_service  # legacy alias
        self._context_center = context_center
        self._runtime_center = runtime_center
        # Phase 7.4: new interaction runtime injection
        self._interaction_orchestrator: Any | None = extra_deps.get("interaction_orchestrator")
        self._invocation_dispatcher: Any | None = extra_deps.get("invocation_dispatcher")
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
        
        # Phase H+: Risk guards
        self._rate_limiter = RateLimiter(RateLimitConfig())
        self._tool_loop_guard = ToolLoopGuard(ToolLoopConfig())
        self._observability = ObservabilityCollector()
        self._context_upload_helper = ContextUploadHelper(ContextUploadConfig())
        self._contract_linter = ContractLinter()
        self._telemetry_service = extra_deps.get("telemetry_service")
        self._pending_task_store = extra_deps.get("pending_task_store")
        self._draft_app_service = extra_deps.get("draft_app_service")
        self._pending_task_orchestrator = extra_deps.get("pending_task_orchestrator")

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
            "call_asset_method": self._handle_runtime_asset_tool,
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
        """Entry point: handles a single incoming message.

        Unified session contract:
        - empty / null session_id => create a new session
        - non-empty session_id => reuse that session
        """
        session = self._memory.create_session(
            user_id=request.user_id,
            channel=request.channel,
            session_id=request.session_id,
        )
        session_id = session.session_id
        pending_task = self._get_latest_pending_task(request.user_id)
        continuation_decision = self._build_continuation_decision(request.message, pending_task)
        self._register_runtime_session(session_id=session_id, user_id=request.user_id, channel=request.channel)
        self._memory.record_user_message(session_id, request.message)
        self._mirror_session_node(session_id=session_id, user_id=request.user_id, channel=request.channel)
        self._append_context_record(session_id=session_id, role="user", content=request.message, kind="message")
        if pending_task is not None:
            self._append_context_record(
                session_id=session_id,
                role="system",
                content=self._render_pending_task_note(pending_task),
                kind="system_note",
            )
        if continuation_decision is not None:
            self._materialize_continuation_decision(
                decision=continuation_decision,
                user_id=request.user_id,
                session_id=session_id,
                message=request.message,
            )
            if pending_task is None:
                pending_task = self._get_latest_pending_task(request.user_id)
            self._append_context_record(
                session_id=session_id,
                role="system",
                content=self._render_continuation_decision_note(continuation_decision),
                kind="system_note",
            )

        # Phase H+: Rate limit check
        allowed, block_reason = self._rate_limiter.is_session_allowed(session_id)
        if not allowed:
            logger.warning(f"Rate limit blocked: session={session_id}, reason={block_reason}")
            # Phase H+: Observability - record blocked command
            from app.utils.observability import CommandMetrics
            self._observability.record_command(CommandMetrics(
                session_id=session_id,
                user_id=request.user_id,
                command_type="receive_message",
                target_app=None,
                status="blocked",
                duration_ms=0,
                tokens_used=0,
                tool_calls=0,
                error=f"Rate limit blocked: {block_reason}",
            ))
            return ChatMessageResponse(
                type="text",
                content=f"请求过于频繁，请稍后再试。{block_reason}",
                session_id=session_id,
            )
        self._rate_limiter.increment_concurrent(session_id)
        self._rate_limiter.record_query(session_id)

        # Phase H+: Observability - start command tracking
        import time as _time
        _cmd_start_time = _time.time()
        _cmd_tool_calls = 0

        # Phase H+: Tool loop guard - reset at command start
        self._tool_loop_guard.reset_command()

        # Phase 7.4: try new interaction runtime first for asset-centered routes
        if continuation_decision is not None and continuation_decision.conversation_mode == "continue_task":
            pending_task = self._advance_pending_task_if_possible(pending_task)
            response = self._build_continue_task_response(session_id, pending_task, continuation_decision)
            self._after_reply(session_id=session_id, reply=response)
            self._auto_save()
            return response

        interaction_result = self._try_new_interaction_chain(request.message)
        if interaction_result is not None:
            return self._build_interaction_response(session_id, request.message, interaction_result, _cmd_start_time)

        # Phase 7.1: interpret intent using interpreter (legacy fallback)
        if hasattr(self._interpreter, "set_tool_registry"):
            self._interpreter.set_tool_registry(self._tool_registry)
        command = self._interpreter.interpret(
            message=request.message,
            available_apps=available_apps or [],
            user_id=request.user_id or "system",
            session_id=session_id,
        )

        # Phase 7.2: enrich command with tools and session state
        available_apps = available_apps or []
        command = self._enrich_command(command, session_id, available_apps)
        if pending_task is not None:
            command.context["pending_task"] = pending_task.model_dump(mode="json")
        if continuation_decision is not None:
            command.context["continuation_decision"] = continuation_decision.model_dump(mode="json")
        self._memory.record_command(session_id, command)

        # Phase 7.3: execute workflow and return reply
        interaction_id = f"lightbrain:{session_id}:{abs(hash(request.message))}"
        result = await self._execute_command(command, session_id, available_apps)
        self._after_reply(session_id=session_id, reply=result)

        if self._telemetry_service is not None:
            self._telemetry_service.record_interaction(
                InteractionTelemetryRecord(
                    interaction_id=interaction_id,
                    session_id=session_id,
                    user_id=request.user_id,
                    app_id=command.target_app,
                    request_type="light_brain_message",
                    success=not result.content.startswith("[Reached max turns"),
                    failure_reason="max_turns_reached" if result.content.startswith("[Reached max turns") else None,
                    total_input_tokens=max(1, len(request.message) // 4),
                    total_output_tokens=max(1, len(result.content) // 4),
                    total_tokens=max(1, (len(request.message) + len(result.content)) // 4),
                    total_latency_ms=int((_time.time() - _cmd_start_time) * 1000),
                    total_tool_calls=_cmd_tool_calls,
                    strategy_name=command.intent,
                )
            )

        # Phase H+: Observability - record command metrics
        _cmd_duration_ms = int((_time.time() - _cmd_start_time) * 1000)
        from app.utils.observability import CommandMetrics
        self._observability.record_command(CommandMetrics(
            session_id=session_id,
            user_id=command.user_id,
            command_type=command.intent,
            target_app=command.target_app,
            status="success" if not result.content.startswith("请求过于频繁") else "blocked",
            duration_ms=_cmd_duration_ms,
            tokens_used=len(result.content) // 4,  # rough estimate
            tool_calls=_cmd_tool_calls,
        ))

        # Phase H+: Rate limit - release concurrent slot
        self._rate_limiter.decrement_concurrent(session_id)

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

        if self._context_center is not None:
            recent_window = self._context_center.get_recent_context(session_id, limit=100)
            command.context["recent_session_context"] = [
                record.model_dump(mode="json") for record in recent_window.records
            ]
            command.context["linked_session_context"] = self._context_center.read_linked_context(session_id, limit=50)
            command.context["child_session_contexts"] = {
                node.session_id: [
                    record.model_dump(mode="json")
                    for record in self._context_center.get_recent_context(node.session_id, limit=50).records
                ]
                for node in self._context_center.get_child_sessions(session_id)
            }

        self._normalize_command_from_context(command)
        return command

    def _normalize_command_from_context(self, command: InterpretedCommand) -> None:
        parameters = dict(command.parameters or {})
        context_hints = command.context.get("context_hints") or []
        if context_hints:
            parameters.setdefault("context_hints", context_hints)

        if command.target_app and not parameters.get("target_app"):
            parameters["target_app"] = command.target_app

        if not parameters.get("related_session_ids"):
            linked = command.context.get("linked_session_context") or {}
            related_ids = [sid for sid in linked.keys() if isinstance(sid, str)]
            if related_ids:
                parameters["related_session_ids"] = related_ids

        command.parameters = parameters

    def _mirror_session_node(self, session_id: str, user_id: str, channel: str) -> None:
        if self._context_center is None:
            return
        self._context_center.register_session_node(
            SessionNode(session_id=session_id, user_id=user_id, channel=channel, kind="root")
        )

    def _register_runtime_session(
        self,
        session_id: str,
        user_id: str,
        channel: str,
        kind: str = "root",
        parent_session_id: str | None = None,
        actor: str = "interaction",
        topic_key: str = "",
    ) -> None:
        if self._runtime_center is None:
            return
        self._runtime_center.register_session(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            kind=kind,
            parent_session_id=parent_session_id,
            actor=actor,
            topic_key=topic_key,
        )

    def _create_child_session(
        self,
        parent_session_id: str,
        child_session_id: str,
        user_id: str,
        channel: str,
        actor: str,
        topic_key: str = "",
    ) -> None:
        self._memory.create_session(user_id=user_id, channel=channel, session_id=child_session_id)
        self._register_runtime_session(
            session_id=child_session_id,
            user_id=user_id,
            channel=channel,
            kind="child",
            parent_session_id=parent_session_id,
            actor=actor,
            topic_key=topic_key,
        )
        if self._context_center is not None:
            self._context_center.register_session_node(
                SessionNode(
                    session_id=child_session_id,
                    user_id=user_id,
                    channel=channel,
                    kind="child",
                    actor=actor,
                    topic_key=topic_key,
                    parent_session_id=parent_session_id,
                )
            )
            self._context_center.link_sessions(
                SessionLink(
                    parent_session_id=parent_session_id,
                    child_session_id=child_session_id,
                    link_type="child",
                    parent_actor="interaction",
                    child_actor=actor,
                    topic_key=topic_key,
                    created_by="gateway",
                )
            )

    def _create_continuation_child_session(
        self,
        parent_session_id: str,
        continuation_session_id: str,
        user_id: str,
        channel: str,
        actor: str,
        topic_key: str = "",
    ) -> None:
        self._memory.create_session(user_id=user_id, channel=channel, session_id=continuation_session_id)
        self._register_runtime_session(
            session_id=continuation_session_id,
            user_id=user_id,
            channel=channel,
            kind="continuation_child",
            parent_session_id=parent_session_id,
            actor=actor,
            topic_key=topic_key,
        )
        if self._context_center is not None:
            self._context_center.register_session_node(
                SessionNode(
                    session_id=continuation_session_id,
                    user_id=user_id,
                    channel=channel,
                    kind="continuation_child",
                    actor=actor,
                    topic_key=topic_key,
                    parent_session_id=parent_session_id,
                )
            )
            self._context_center.link_sessions(
                SessionLink(
                    parent_session_id=parent_session_id,
                    child_session_id=continuation_session_id,
                    link_type="continuation",
                    parent_actor=actor,
                    child_actor=actor,
                    topic_key=topic_key,
                    created_by="gateway",
                )
            )

    def _run_local_child_handler(
        self,
        *,
        parent_session_id: str,
        user_id: str,
        topic_key: str,
        channel: str,
        system_note: str,
        build_response,
    ) -> ChatMessageResponse:
        child_session_id = f"{parent_session_id}.local.{topic_key}"
        self._create_child_session(
            parent_session_id=parent_session_id,
            child_session_id=child_session_id,
            user_id=user_id,
            channel=channel,
            actor="interaction",
            topic_key=topic_key,
        )
        self._append_context_record(
            session_id=child_session_id,
            role="system",
            content=system_note,
            kind="system_note",
        )
        response = build_response(child_session_id)
        self._after_reply(session_id=child_session_id, reply=response)
        return response

    def _after_reply(self, session_id: str, reply: ChatMessageResponse) -> None:
        self._memory.record_reply(session_id, reply)
        if reply.content:
            self._append_context_record(
                session_id=session_id,
                role="assistant",
                content=reply.content,
                kind="message",
            )

    # Phase 7.4: new interaction runtime bridge
    def _try_new_interaction_chain(self, message: str) -> dict[str, Any] | None:
        """Try the new asset-centered interaction runtime. Returns None if fallback needed."""
        if self._interaction_orchestrator is None:
            return None
        try:
            result = self._interaction_orchestrator.process_message(message)
        except Exception as exc:
            logger.warning("Interaction orchestrator error, falling back: %s", exc)
            return None
        action = result.get("resolved_action")
        metadata = result.get("metadata", {})
        if action == "invoke_method":
            invoke = result.get("invoke")
            if invoke and self._invocation_dispatcher is not None:
                try:
                    execution = self._invocation_dispatcher.dispatch(
                        asset_id=invoke["asset_id"],
                        method=invoke["method"],
                        params=invoke.get("params") or {},
                    )
                    return {
                        "action": "invoke_executed",
                        "invoke": invoke,
                        "execution": execution,
                        "metadata": metadata,
                    }
                except Exception as exc:
                    logger.warning("Invocation dispatch error: %s", exc)
                    return {"action": "invoke_error", "error": str(exc), "metadata": metadata}
        if action == "reply_text":
            # Only claim the new-chain reply for specific recognized routes;
            # generic fallback text means "no route matched" → let legacy handle it.
            if metadata.get("route"):
                text = result.get("text") or "请告诉我你想做什么，例如查看状态、了解某个资产、或者执行某个操作。"
                return {"action": "reply_text", "text": text, "metadata": metadata}
            return None
        if action == "load_detail":
            detail_id = result.get("need_asset_detail_id")
            return {"action": "load_detail", "need_asset_detail_id": detail_id, "metadata": metadata}
        # Unknown action — fallback to legacy interpreter
        return None

    def _build_interaction_response(
        self,
        session_id: str,
        raw_message: str,
        interaction_result: dict[str, Any],
        cmd_start_time: float,
    ) -> ChatMessageResponse:
        """Convert new interaction runtime result to ChatMessageResponse."""
        action = interaction_result["action"]
        if action == "invoke_executed":
            invoke = interaction_result.get("invoke", {})
            execution = interaction_result["execution"]
            if execution.get("ok"):
                result_data = execution.get("execution", {}).get("result", "")
                # Phase 7.4: use specialized renderers for self-iteration assets
                asset_id = invoke.get("asset_id", "")
                method = invoke.get("method", "")
                if asset_id == "asset:self_iteration_center:v1":
                    rendered = self._render_self_iteration_invoke_result(method, result_data)
                    if rendered:
                        return ChatMessageResponse(type="text", content=rendered, session_id=session_id)
                if isinstance(result_data, dict):
                    content = json.dumps(result_data, ensure_ascii=False, indent=2)
                elif isinstance(result_data, list):
                    content = json.dumps(result_data, ensure_ascii=False, indent=2)
                else:
                    content = str(result_data)
            else:
                content = f"调用失败: {execution.get('error', '未知错误')}"
            return ChatMessageResponse(type="text", content=content, session_id=session_id)
        if action == "invoke_error":
            return ChatMessageResponse(
                type="text",
                content=f"执行出错: {interaction_result.get('error', '未知错误')}",
                session_id=session_id,
            )
        if action == "load_detail":
            detail_id = interaction_result.get("need_asset_detail_id", "")
            return ChatMessageResponse(
                type="text",
                content=f"需要加载资产详情: {detail_id}",
                session_id=session_id,
            )
        # reply_text or fallback
        text = interaction_result.get("text", "请告诉我你想做什么。")
        return ChatMessageResponse(type="text", content=text, session_id=session_id)

    def _render_self_iteration_invoke_result(self, method: str, result_data: Any) -> str | None:
        """Render self-iteration invoke result using specialized formatters."""
        if method in ("get_self_iteration_strategy_overview", "strategy_overview") and isinstance(result_data, dict):
            return render_self_iteration_strategy_overview(result_data)
        if method == "list_self_iteration_assets" and isinstance(result_data, list):
            return render_self_iteration_asset_list(result_data)
        if method == "query_self_iteration_asset" and isinstance(result_data, dict):
            return render_self_iteration_asset_detail(result_data)
        return None

    def _append_context_record(self, session_id: str, role: str, content: str, kind: str = "message") -> None:
        """Append context record with whitelist validation (Phase H+ risk guard)."""
        if self._context_center is None:
            return
        
        # Validate content against whitelist (Phase H+ risk guard)
        try:
            from app.utils.context_upload import is_content_allowed_for_upload
            allowed, reason = is_content_allowed_for_upload(content, kind, role)
            if not allowed:
                logger.warning(f"Context upload blocked by whitelist: kind={kind}, role={role}, reason={reason}")
                # Still allow system notes for critical logging, but truncate if needed
                if kind != "system_note":
                    return
        except Exception as e:
            logger.error(f"Context upload validation error: {e}")
        
        self._context_center.append_context(
            SessionContextRecord(session_id=session_id, role=role, content=content, kind=kind)
        )

    def _link_related_sessions(self, parent_session_id: str, child_session_id: str, created_by: str = "system") -> None:
        if self._context_center is None or parent_session_id == child_session_id:
            return
        self._context_center.link_sessions(
            SessionLink(
                parent_session_id=parent_session_id,
                child_session_id=child_session_id,
                link_type="related",
                created_by=created_by,
            )
        )

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
            bridge_session_id = session_id
            if command.intent in {"create_app", "modify_app", "delete_app", "start_app", "stop_app", "pause_app", "resume_app", "query_app"}:
                bridge_session_id = f"{session_id}.orch.{command.intent}"
                self._create_child_session(
                    parent_session_id=session_id,
                    child_session_id=bridge_session_id,
                    user_id=command.user_id or "system",
                    channel="orchestration",
                    actor="orchestration",
                    topic_key=command.intent,
                )
                self._append_context_record(
                    session_id=bridge_session_id,
                    role="system",
                    content=f"bridge_dispatch:{command.intent}",
                    kind="system_note",
                )
            try:
                bridge_result = await self._orchestrator_bridge.execute_command(
                    user_id=command.user_id or "",
                    app_instance_id="default",
                    text=command.raw_input or "",
                    session_id=bridge_session_id,
                )
                if bridge_result is not None:
                    if bridge_session_id != session_id:
                        self._append_context_record(
                            session_id=bridge_session_id,
                            role="assistant",
                            content=bridge_result.get("content", ""),
                            kind="message",
                        )
                    return ChatMessageResponse(
                        type=bridge_result.get("type", "text"),
                        content=bridge_result.get("content", ""),
                        session_id=bridge_session_id,
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
            "call_asset_method": self._handle_runtime_asset_tool,
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
            "package_list_installed": self._handle_package_list_installed,
            "package_show": self._handle_package_show,
            "package_build": self._handle_package_build,
            "package_install": self._handle_package_install,
            "package_uninstall": self._handle_package_uninstall,
            "package_rollback": self._handle_package_rollback,
            "package_search": self._handle_package_search,
            "master_execute": self._handle_master_execute,
        }

        # 统一 handler 字典：没有精确匹配的意图全部透传给 ToolCallingEngine（LLM 决定）
        # 当 ToolCallingEngine 返回 direct_response / unclear 时，由这里兜底生成友好回复
        def _llm_fallback_handler(command: InterpretedCommand, session_id: str, apps: list[dict]) -> ChatMessageResponse:
            text = command.parameters.get("text") or command.parameters.get("reply", "")
            structured_answer = getattr(command, "structured_answer", None)
            self_model = getattr(structured_answer, "self_model", None) if structured_answer else None
            answer_mode = getattr(self_model, "answer_mode", "direct") if self_model else "direct"
            verification_mode = getattr(self_model, "verification_mode", "none") if self_model else "none"
            unverified_points = getattr(structured_answer, "unverified_points", []) if structured_answer else []

            if not text:
                text = "我明白了。有什么我可以帮你的吗？"

            if answer_mode == "clarification_required":
                hint = unverified_points[0] if unverified_points else "当前信息还不够完整，需要你补充一个关键点。"
                text = f"当前还不能直接下结论。{hint}"
            elif answer_mode == "verification_required":
                prefix = "当前结论仍需进一步验证。"
                if verification_mode == "light":
                    prefix = "当前结论建议做轻量验证。"
                text = f"{prefix}{text}" if text else prefix
            elif answer_mode == "tool_required" and verification_mode == "light":
                text = f"以下结论基于当前工具证据，仍建议做轻量验证。{text}" if text else "以下结论基于当前工具证据，仍建议做轻量验证。"

            return ChatMessageResponse(type="text", content=text, session_id=session_id, structured_answer=structured_answer)

        handler = local_handlers.get(command.intent)
        if handler:
            return await handler(command, session_id, available_apps)

        # 没有精确 handler → 透传给 LLM fallback handler（direct_response, unclear, 任意未知意图）
        if command.intent in ("direct_response", "unclear", "clarification_pending"):
            return _llm_fallback_handler(command, session_id, available_apps)

        return _llm_fallback_handler(command, session_id, available_apps)

    def _build_default_tool_registry(self):
        from app.services.tool_registry import ToolRegistry, ToolDefinition, ToolParameter
        registry = ToolRegistry()

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
        modify_session_id = f"{session_id}.local.modify_interactive_app"
        self._create_child_session(
            parent_session_id=session_id,
            child_session_id=modify_session_id,
            user_id=command.user_id or "web-user",
            channel="interactive_app",
            actor="interaction",
            topic_key="modify_interactive_app",
        )
        self._append_context_record(
            session_id=modify_session_id,
            role="system",
            content=f"local_handler:modify_interactive_app:{user_request}",
            kind="system_note",
        )

        try:
            if hasattr(self, "_interactive_app_workflow") and self._interactive_app_workflow:
                result = self._interactive_app_workflow.modify_app(
                    user_id=command.user_id or "web-user",
                    user_request=user_request,
                    auto_activate=True,
                    require_confirmation=False,
                )
                content = f"✅ 界面已更新！\n\n修改内容: {user_request}\n新版本: {result['new_version']}\n修改文件: {', '.join(result['files_changed'])}\n\n请刷新页面查看新界面。"
                self._append_context_record(
                    session_id=modify_session_id,
                    role="assistant",
                    content=content,
                    kind="message",
                )
                return ChatMessageResponse(
                    type="card",
                    content=content,
                    session_id=modify_session_id,
                    actions=[
                        ActionSuggestion(id="query_status", label="📊 系统状态", action_type="execute", payload={"intent": "query_status"}, style="secondary"),
                    ],
                )
            else:
                content = "⚠️ 交互式 App 修改工作流未加载，无法执行自修改。"
                self._append_context_record(
                    session_id=modify_session_id,
                    role="assistant",
                    content=content,
                    kind="message",
                )
                return ChatMessageResponse(
                    type="text",
                    content=content,
                    session_id=modify_session_id,
                    requires_input=False,
                )
        except Exception as e:
            content = f"❌ 修改失败: {str(e)}\n\n请稍后重试。"
            self._append_context_record(
                session_id=modify_session_id,
                role="assistant",
                content=content,
                kind="message",
            )
            return ChatMessageResponse(
                type="text",
                content=content,
                session_id=modify_session_id,
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

    def _render_self_iteration_asset_tool_reply(
        self,
        command: InterpretedCommand,
        payload: dict[str, Any],
        data: Any,
    ) -> str | None:
        asset_id = payload.get("asset_id") or command.target_app
        if asset_id != "asset:self_iteration_center:v1":
            return None

        if command.intent in {"query_asset_info", "query_asset_detail"} and isinstance(data, dict):
            capabilities = data.get("capabilities") if isinstance(data.get("capabilities"), list) else []
            if not capabilities and getattr(self, "_runtime_center", None):
                try:
                    runtime_info = self._runtime_center.query_asset_info("asset:self_iteration_center:v1")
                    if isinstance(runtime_info, dict) and isinstance(runtime_info.get("capabilities"), list):
                        capabilities = runtime_info.get("capabilities")
                except Exception:
                    capabilities = capabilities or []
            return render_asset_info_summary(
                asset_id=str(asset_id),
                intro="self_iteration_center 是自我迭代资产入口。",
                capabilities=capabilities,
                extra_lines=[
                    "- 系统视角: Observe(回归/在线观察) → Summarize(治理总览) → Act(trigger/backlog)",
                    "- 用途: 汇总并查询 regression、observation、governance、refinement 这条自我迭代链的资产摘要",
                ],
            )

        if command.intent == "call_asset_method" and isinstance(data, dict):
            method = data.get("method") or payload.get("method")
            result_payload = data.get("result")
            if method == "get_self_iteration_strategy_overview" and isinstance(result_payload, dict):
                return render_self_iteration_strategy_overview(result_payload)
            if method == "list_self_iteration_assets" and isinstance(result_payload, list):
                return render_self_iteration_asset_list(result_payload)
            if method == "query_self_iteration_asset" and isinstance(result_payload, dict):
                return render_self_iteration_asset_detail(result_payload)
        return None

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
        # Phase H+: Tool loop guard check before tool execution
        import time as _time
        _cmd_tool_calls = getattr(self, '_cmd_tool_calls', 0)
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, 
            dict(command.parameters or {}), 
            _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            # Phase H+: Observability - record blocked command
            from app.utils.observability import CommandMetrics
            self._observability.record_command(CommandMetrics(
                session_id=session_id,
                user_id=command.user_id,
                command_type=command.intent,
                target_app=command.target_app,
                status="blocked",
                duration_ms=0,
                tokens_used=0,
                tool_calls=0,
                error=f"Tool loop guard blocked: {block_reason}",
            ))
            return ChatMessageResponse(
                type="text",
                content=f"工具调用过于频繁或出现循环，已阻断。{block_reason}",
                session_id=session_id,
                requires_input=False,
            )
        
        # Phase H+: Contract linter validation before tool execution
        if command.parameters:
            lint_result = self._contract_linter.validate_tool_args(
                command.intent,
                dict(command.parameters or {})
            )
            if not lint_result.is_valid:
                logger.warning(f"Contract lint failed: session={session_id}, tool={command.intent}, errors={lint_result.errors}")
                # Phase H+: Observability - record rejected command
                from app.utils.observability import CommandMetrics
                self._observability.record_command(CommandMetrics(
                    session_id=session_id,
                    user_id=command.user_id,
                    command_type=command.intent,
                    target_app=command.target_app,
                    status="blocked",
                    duration_ms=0,
                    tokens_used=0,
                    tool_calls=0,
                    error=f"Contract validation failed: {'; '.join(lint_result.errors)}",
                ))
                return ChatMessageResponse(
                    type="text",
                    content=f"参数校验失败: {'; '.join(lint_result.errors)}",
                    session_id=session_id,
                    requires_input=False,
                )
        
        # Record tool call after check passes
        self._tool_loop_guard.record_call(
            command.intent,
            dict(command.parameters or {}),
            _time.time()
        )
        
        if not self._asset_tool_executor:
            return self._error_reply(session_id, "⚠️ 运行态资产工具模块未加载。")
        caller_id = f"user.{command.user_id}" if command.user_id else "system"
        payload = dict(command.parameters or {})
        if command.intent == "call_asset_method" and not payload.get("method"):
            return ChatMessageResponse(
                type="text",
                content="你想调用哪个方法？请告诉我要调用的 method 名称。",
                session_id=session_id,
                requires_input=True,
            )
        
        result = self._asset_tool_executor.execute(
            command.intent, payload, caller_id
        )
        if not result.success:
            return self._error_reply(session_id, f"❌ {result.error}")
        rendered_content = self._render_self_iteration_asset_tool_reply(command, payload, result.data)
        return ChatMessageResponse(
            type="text",
            content=rendered_content or json.dumps(result.data, ensure_ascii=False, indent=2),
            session_id=session_id,
            requires_input=False,
        )


    def _handle_package_list_installed(self, command, session_id, apps):
        # Phase H+: Tool loop guard check
        import time as _time
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, dict(command.parameters or {}), _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            return self._error_reply(session_id, f"工具调用过于频繁或出现循环，已阻断。{block_reason}")
        self._tool_loop_guard.record_call(command.intent, dict(command.parameters or {}), _time.time())
        
        if not self._package_manager_executor:
            return self._error_reply(session_id, render_management_availability("包管理模块"))

        def build_response(child_session_id: str) -> ChatMessageResponse:
            result = self._package_manager_executor.execute("package_list_installed", command.parameters)
            if result.success:
                packages = result.data.get("packages", [])
                if not packages:
                    return ChatMessageResponse(
                        type="text",
                        content="📦 当前没有已安装的包。\n\n可用 package_search 搜索可安装的包。",
                        session_id=child_session_id,
                        requires_input=False,
                    )
                return ChatMessageResponse(
                    type="text",
                    content=render_package_list(packages, header="📦 **已安装的包：**\n"),
                    session_id=child_session_id,
                    requires_input=False,
                )
            return self._error_reply(child_session_id, render_management_status("failure", "query", error=result.error))

        return self._run_local_child_handler(
            parent_session_id=session_id,
            user_id=command.user_id or "system",
            topic_key="package_list_installed",
            channel="package_manager",
            system_note="local_handler:package_list_installed",
            build_response=build_response,
        )

    def _handle_package_show(self, command, session_id, apps):
        # Phase H+: Tool loop guard check
        import time as _time
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, dict(command.parameters or {}), _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            return self._error_reply(session_id, f"工具调用过于频繁或出现循环，已阻断。{block_reason}")
        self._tool_loop_guard.record_call(command.intent, dict(command.parameters or {}), _time.time())
        
        if not self._package_manager_executor:
            return self._error_reply(session_id, render_management_availability("包管理模块"))

        def build_response(child_session_id: str) -> ChatMessageResponse:
            result = self._package_manager_executor.execute("package_show", command.parameters)
            if result.success:
                d = result.data
                return ChatMessageResponse(
                    type="text",
                    content=render_package_detail(d),
                    session_id=child_session_id,
                    requires_input=False,
                )
            return self._error_reply(child_session_id, render_management_status("failure", "query", error=result.error))

        return self._run_local_child_handler(
            parent_session_id=session_id,
            user_id=command.user_id or "system",
            topic_key="package_show",
            channel="package_manager",
            system_note="local_handler:package_show",
            build_response=build_response,
        )

    def _handle_package_build(self, command, session_id, apps):
        # Phase H+: Tool loop guard check
        import time as _time
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, dict(command.parameters or {}), _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            return self._error_reply(session_id, f"工具调用过于频繁或出现循环，已阻断。{block_reason}")
        self._tool_loop_guard.record_call(command.intent, dict(command.parameters or {}), _time.time())
        
        if not self._package_manager_executor:
            return self._error_reply(session_id, render_management_availability("包管理模块"))

        def build_response(child_session_id: str) -> ChatMessageResponse:
            result = self._package_manager_executor.execute("package_build", command.parameters)
            if result.success:
                d = result.data
                return ChatMessageResponse(
                    type="text",
                    content=render_package_operation_result("build", d),
                    session_id=child_session_id,
                    requires_input=False,
                )
            return self._error_reply(child_session_id, render_management_status("failure", "build", error=result.error))

        return self._run_local_child_handler(
            parent_session_id=session_id,
            user_id=command.user_id or "system",
            topic_key="package_build",
            channel="package_manager",
            system_note="local_handler:package_build",
            build_response=build_response,
        )

    def _handle_package_install(self, command, session_id, apps):
        # Phase H+: Tool loop guard check
        import time as _time
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, dict(command.parameters or {}), _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            return self._error_reply(session_id, f"工具调用过于频繁或出现循环，已阻断。{block_reason}")
        self._tool_loop_guard.record_call(command.intent, dict(command.parameters or {}), _time.time())
        
        if not self._package_manager_executor:
            return self._error_reply(session_id, render_management_availability("包管理模块"))

        def build_response(child_session_id: str) -> ChatMessageResponse:
            result = self._package_manager_executor.execute("package_install", command.parameters)
            if result.success:
                d = result.data
                return ChatMessageResponse(
                    type="text",
                    content=render_package_operation_result("install", d),
                    session_id=child_session_id,
                    requires_input=False,
                )
            return self._error_reply(child_session_id, render_management_status("failure", "install", error=result.error))

        return self._run_local_child_handler(
            parent_session_id=session_id,
            user_id=command.user_id or "system",
            topic_key="package_install",
            channel="package_manager",
            system_note="local_handler:package_install",
            build_response=build_response,
        )

    def _handle_package_uninstall(self, command, session_id, apps):
        # Phase H+: Tool loop guard check
        import time as _time
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, dict(command.parameters or {}), _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            return self._error_reply(session_id, f"工具调用过于频繁或出现循环，已阻断。{block_reason}")
        self._tool_loop_guard.record_call(command.intent, dict(command.parameters or {}), _time.time())
        
        if not self._package_manager_executor:
            return self._error_reply(session_id, render_management_availability("包管理模块"))

        def build_response(child_session_id: str) -> ChatMessageResponse:
            result = self._package_manager_executor.execute("package_uninstall", command.parameters)
            if result.success:
                return ChatMessageResponse(
                    type="text",
                    content=render_management_status(
                        "success",
                        "uninstall",
                        subject=command.parameters.get("asset_id", "unknown"),
                    ),
                    session_id=child_session_id,
                    requires_input=False,
                )
            return self._error_reply(child_session_id, render_management_status("failure", "uninstall", error=result.error))

        return self._run_local_child_handler(
            parent_session_id=session_id,
            user_id=command.user_id or "system",
            topic_key="package_uninstall",
            channel="package_manager",
            system_note="local_handler:package_uninstall",
            build_response=build_response,
        )

    def _handle_package_rollback(self, command, session_id, apps):
        # Phase H+: Tool loop guard check
        import time as _time
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, dict(command.parameters or {}), _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            return self._error_reply(session_id, f"工具调用过于频繁或出现循环，已阻断。{block_reason}")
        self._tool_loop_guard.record_call(command.intent, dict(command.parameters or {}), _time.time())
        
        if not self._package_manager_executor:
            return self._error_reply(session_id, render_management_availability("包管理模块"))

        def build_response(child_session_id: str) -> ChatMessageResponse:
            result = self._package_manager_executor.execute("package_rollback", command.parameters)
            if result.success:
                d = result.data
                return ChatMessageResponse(
                    type="text",
                    content=render_package_operation_result("rollback", d),
                    session_id=child_session_id,
                    requires_input=False,
                )
            return self._error_reply(child_session_id, render_management_status("failure", "rollback", error=result.error))

        return self._run_local_child_handler(
            parent_session_id=session_id,
            user_id=command.user_id or "system",
            topic_key="package_rollback",
            channel="package_manager",
            system_note="local_handler:package_rollback",
            build_response=build_response,
        )

    def _handle_package_search(self, command, session_id, apps):
        # Phase H+: Tool loop guard check
        import time as _time
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, dict(command.parameters or {}), _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            return self._error_reply(session_id, f"工具调用过于频繁或出现循环，已阻断。{block_reason}")
        self._tool_loop_guard.record_call(command.intent, dict(command.parameters or {}), _time.time())
        
        if not self._package_manager_executor:
            return self._error_reply(session_id, render_management_availability("包管理模块"))

        def build_response(child_session_id: str) -> ChatMessageResponse:
            result = self._package_manager_executor.execute("package_search", command.parameters)
            if result.success:
                packages = result.data.get("packages", [])
                if not packages:
                    return ChatMessageResponse(
                        type="text",
                        content=f"🔍 未找到与 '{command.parameters.get('query', '')}' 匹配的包。",
                        session_id=child_session_id,
                        requires_input=False,
                    )
                return ChatMessageResponse(
                    type="text",
                    content=render_package_list(
                        packages,
                        header=f"🔍 搜索结果（{len(packages)} 个）:\n",
                        include_install_status=True,
                    ),
                    session_id=child_session_id,
                    requires_input=False,
                )
            return self._error_reply(child_session_id, render_management_status("failure", "search", error=result.error))

        return self._run_local_child_handler(
            parent_session_id=session_id,
            user_id=command.user_id or "system",
            topic_key="package_search",
            channel="package_manager",
            system_note="local_handler:package_search",
            build_response=build_response,
        )

    def _handle_master_execute(self, command, session_id, apps):
        # Phase H+: Tool loop guard check
        import time as _time
        allowed, block_reason = self._tool_loop_guard.check_allowed(
            command.intent, dict(command.parameters or {}), _time.time()
        )
        if not allowed:
            logger.warning(f"Tool loop guard blocked: session={session_id}, tool={command.intent}, reason={block_reason}")
            return self._error_reply(session_id, f"工具调用过于频繁或出现循环，已阻断。{block_reason}")
        self._tool_loop_guard.record_call(command.intent, dict(command.parameters or {}), _time.time())
        
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
        master_session_id = f"{session_id}.master.{operation}"
        self._create_child_session(
            parent_session_id=session_id,
            child_session_id=master_session_id,
            user_id=user_id,
            channel="master_control",
            actor="orchestration",
            topic_key=operation,
        )
        self._append_context_record(
            session_id=master_session_id,
            role="system",
            content=f"master_execute:{operation}",
            kind="system_note",
        )
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
                return ChatMessageResponse(
                    type="text",
                    content=f"❌ 权限不足: {message}" + (f"\n需要 {result.get('required_role', '')} 角色。" if result.get("required_role") else ""),
                    session_id=master_session_id,
                    requires_input=False,
                )
            elif status == "success":
                content = f"✅ {message or '操作成功'}"
                if data:
                    content += f"\n\n{json.dumps(data, ensure_ascii=False, indent=2)}"
                self._append_context_record(session_id=master_session_id, role="assistant", content=content, kind="message")
                return ChatMessageResponse(
                    type="text",
                    content=content,
                    session_id=master_session_id,
                    requires_input=False,
                )
            elif status == "delegated":
                content = f"ℹ️ {message}"
                if data:
                    content += f"\n\n{json.dumps(data, ensure_ascii=False, indent=2)}"
                self._append_context_record(session_id=master_session_id, role="assistant", content=content, kind="message")
                return ChatMessageResponse(
                    type="text",
                    content=content,
                    session_id=master_session_id,
                    requires_input=False,
                )
            else:
                return self._error_reply(master_session_id, f"❌ {message or f'操作失败: {status}'}")
        return self._error_reply(master_session_id, "⚠️ 主控返回了意外结果。")

    async def _handle_list_apps(
        self, command: InterpretedCommand, session_id: str, apps: list[dict],
    ) -> ChatMessageResponse:
        """Handle list_apps intent — show available apps."""
        list_session_id = f"{session_id}.local.list_apps"
        self._create_child_session(
            parent_session_id=session_id,
            child_session_id=list_session_id,
            user_id=command.user_id or "system",
            channel="local_gateway",
            actor="interaction",
            topic_key="list_apps",
        )
        self._append_context_record(
            session_id=list_session_id,
            role="system",
            content="local_handler:list_apps",
            kind="system_note",
        )
        if not apps:
            content = "📱 你还没有任何 App。\n\n对我说「帮我建一个监控 App」来创建你的第一个应用。"
            self._append_context_record(session_id=list_session_id, role="assistant", content=content, kind="message")
            return ChatMessageResponse(
                type="text",
                content=content,
                session_id=list_session_id,
                actions=[
                    ActionSuggestion(id="create_app", label="➕ 创建 App", action_type="navigate", payload={"intent": "create_app"}, style="primary"),
                ],
            )
        content = render_app_list(apps)
        self._append_context_record(session_id=list_session_id, role="assistant", content=content, kind="message")
        return ChatMessageResponse(
            type="list",
            content=content,
            session_id=list_session_id,
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

    def _get_latest_pending_task(self, user_id: str | None) -> PendingTaskRecord | None:
        if self._pending_task_store is None or not user_id:
            return None
        try:
            return self._pending_task_store.get_latest_open_task(user_id)
        except Exception as e:
            logger.warning("Failed to load pending task for %s: %s", user_id, e)
            return None

    def _build_continuation_decision(
        self,
        message: str,
        pending_task: PendingTaskRecord | None,
    ) -> TaskContinuationDecision | None:
        stripped = (message or "").strip()
        if not stripped:
            return None
        if pending_task is not None and stripped in {"继续", "开始执行", "按刚才那个继续", "结合之前记录继续"}:
            return TaskContinuationDecision(
                conversation_mode="continue_task",
                pending_task_id=pending_task.task_id,
                target_ref=pending_task.target_ref,
                next_action=pending_task.next_recommended_action or {"type": "resume_pending_task"},
                missing_fields=list(pending_task.missing_fields),
                confidence=0.9,
            )
        if pending_task is None and any(token in stripped for token in ["创建", "新建", "做一个", "搞一个"]) and any(
            token.lower() in stripped.lower() for token in ["app", "应用", "程序", "模块"]
        ):
            inferred_name = "draft_app"
            for token in ["写代码", "天气", "提醒", "日志", "监控"]:
                if token in stripped:
                    inferred_name = f"{token}_app"
                    break
            return TaskContinuationDecision(
                conversation_mode="draft_create",
                draft_proposal={
                    "name": inferred_name,
                    "source_message": stripped,
                },
                next_action={"type": "create_draft_app"},
                confidence=0.6,
            )
        return None

    def _materialize_continuation_decision(
        self,
        decision: TaskContinuationDecision,
        user_id: str,
        session_id: str,
        message: str,
    ) -> None:
        if decision.conversation_mode != "draft_create":
            return
        if self._draft_app_service is None or self._pending_task_store is None:
            return
        existing_task = self._pending_task_store.get_latest_open_task(user_id)
        if existing_task is not None and existing_task.intent == "create_app" and existing_task.status in {"drafted", "pending_input", "ready_to_execute"}:
            decision.pending_task_id = existing_task.task_id
            decision.target_ref = dict(existing_task.target_ref)
            decision.missing_fields = list(existing_task.missing_fields)
            decision.next_action = existing_task.next_recommended_action or decision.next_action
            return
        draft_name = decision.draft_proposal.get("name") or "draft_app"
        draft_goal = decision.draft_proposal.get("source_message") or message
        draft_app = self._draft_app_service.create_draft_app(
            owner_user_id=user_id,
            name=draft_name,
            goal=draft_goal,
        )
        decision.target_ref = {"app_id": draft_app.id, "target_id": draft_app.id}
        from app.models.pending_task import PendingTaskRecord
        pending_task = PendingTaskRecord(
            task_id=f"pt_{draft_app.id}",
            user_id=user_id,
            session_id=session_id,
            intent="create_app",
            status="drafted",
            draft_payload={
                "name": draft_name,
                "source_message": message,
            },
            target_ref={"app_id": draft_app.id, "target_id": draft_app.id},
            missing_fields=["runtime_profile", "execution_mode"],
            next_recommended_action={"type": "continue_draft_app_setup", "app_id": draft_app.id},
            last_user_message=message,
        )
        self._pending_task_store.upsert_task(pending_task)
        decision.pending_task_id = pending_task.task_id
        decision.missing_fields = list(pending_task.missing_fields)

    def _render_pending_task_note(self, task: PendingTaskRecord) -> str:
        target = task.target_ref.get("target_id") or task.target_ref.get("app_id") or "unknown"
        missing = ", ".join(task.missing_fields) if task.missing_fields else "none"
        return (
            f"pending_task task_id={task.task_id} intent={task.intent} status={task.status} "
            f"target={target} missing_fields={missing}"
        )

    def _render_continuation_decision_note(self, decision: TaskContinuationDecision) -> str:
        return (
            f"continuation_decision mode={decision.conversation_mode} "
            f"pending_task_id={decision.pending_task_id or 'none'} confidence={decision.confidence:.2f}"
        )

    def _build_continue_task_response(
        self,
        session_id: str,
        pending_task: PendingTaskRecord | None,
        decision: TaskContinuationDecision,
    ) -> ChatMessageResponse:
        if pending_task is None:
            return ChatMessageResponse(
                type="text",
                content="我没有找到可继续的未完成任务。你可以直接告诉我现在想做什么。",
                session_id=session_id,
            )
        target_id = pending_task.target_ref.get("app_id") or pending_task.target_ref.get("target_id") or "unknown"
        missing = "、".join(pending_task.missing_fields) if pending_task.missing_fields else "无"
        next_step = pending_task.next_recommended_action.get("type") if pending_task.next_recommended_action else "resume_pending_task"
        if next_step == "draft_ready_reported" or pending_task.status == "completed":
            content = (
                f"草案任务已经准备完成。\n"
                f"当前目标：{target_id}\n"
                f"当前状态：{pending_task.status}\n"
                f"下一步：可以把这个 draft app 接入正式 App 生命周期。"
            )
            return ChatMessageResponse(
                type="progress",
                content=content,
                session_id=session_id,
                data={
                    "pending_task": pending_task.model_dump(mode="json"),
                    "continuation_decision": decision.model_dump(mode="json"),
                },
                requires_input=False,
            )
        content = (
            f"我已经恢复上次未完成的任务：{pending_task.intent}。\n"
            f"当前目标：{target_id}\n"
            f"当前状态：{pending_task.status}\n"
            f"还缺字段：{missing}\n"
            f"下一步建议：{next_step}"
        )
        return ChatMessageResponse(
            type="progress",
            content=content,
            session_id=session_id,
            data={
                "pending_task": pending_task.model_dump(mode="json"),
                "continuation_decision": decision.model_dump(mode="json"),
            },
            requires_input=bool(pending_task.missing_fields),
        )

    def _advance_pending_task_if_possible(self, pending_task: PendingTaskRecord | None) -> PendingTaskRecord | None:
        if self._pending_task_orchestrator is not None:
            return self._pending_task_orchestrator.advance_if_possible(pending_task)
        if pending_task is None or self._pending_task_store is None:
            return pending_task
        missing_fields = list(pending_task.missing_fields)
        known_facts = dict(pending_task.known_facts)
        changed = False
        if "runtime_profile" in missing_fields and "runtime_profile" not in known_facts:
            known_facts["runtime_profile"] = "default"
            missing_fields.remove("runtime_profile")
            changed = True
        if "execution_mode" in missing_fields and "execution_mode" not in known_facts:
            known_facts["execution_mode"] = "service"
            missing_fields.remove("execution_mode")
            changed = True
        if not changed and not missing_fields and pending_task.status != "ready_to_execute":
            changed = True
        if not changed:
            return pending_task
        new_status = "ready_to_execute" if not missing_fields else pending_task.status
        next_action = {"type": "execute_draft_app_setup"} if not missing_fields else pending_task.next_recommended_action
        updated = pending_task.model_copy(update={
            "known_facts": known_facts,
            "missing_fields": missing_fields,
            "status": new_status,
            "next_recommended_action": next_action,
        })
        self._pending_task_store.upsert_task(updated)
        return updated

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

    # Transitional Phase H path: prefer RuntimeCenter for session entity truth,
    # fall back to LightBrainMemory while active-path migration is incomplete.
    def list_sessions(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """List sessions for a user (or all if user_id is None)."""
        if self._runtime_center is not None:
            return [node.model_dump(mode="json") for node in self._runtime_center.list_sessions(user_id)]
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
        action_session_id = action_params.get("session_id") or session_id

        if action_session_id != session_id:
            self._memory.create_session(user_id=user_id, channel="action", session_id=action_session_id)
            self._register_runtime_session(session_id=action_session_id, user_id=user_id, channel="action")
            self._mirror_session_node(session_id=action_session_id, user_id=user_id, channel="action")
            self._link_related_sessions(parent_session_id=session_id, child_session_id=action_session_id, created_by="action")

        self._append_context_record(
            session_id=action_session_id,
            role="user",
            content=f"action:{action_id}",
            kind="system_note",
        )

        from app.models.chat import InterpretedCommand

        command = InterpretedCommand(
            intent=intent,
            confidence=1.0 if intent != "unclear" else 0.0,
            target_app=(action_params.get("target_app") or target or None),
            parameters=dict(action_params.get("parameters") or {}),
            user_id=user_id,
            raw_input=f"action:{action_id}",
        )
        command = self._enrich_command(command, action_session_id, [])
        self._memory.record_command(action_session_id, command)
        result = await self._execute_command(command, action_session_id, [])
        self._after_reply(session_id=action_session_id, reply=result)
        self._auto_save()
        return result
