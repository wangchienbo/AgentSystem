"""Gateway ↔ Orchestrator Bridge.

Central integration layer connecting LightBrainGateway to the new
G.1/G.2 module chain: AppOrchestrator → MessageBus → Skill Workers → LogCenter.

This is the bridge that makes the full execution chain work:
  User → Gateway → Bridge → Orchestrator → Bus → Workers → LogCenter

Preserves backward compatibility: if the new chain is unavailable,
falls back to the existing hardcoded handler dict in the Gateway.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from app.core.message_bus import MessageBus
from app.core.simple_worker import SimpleWorker
from app.core.skill_worker import SkillWorker
from app.core.worker_manager import WorkerManager
from app.models.app_binding import AppInstanceBinding
from app.models.log_center import LogCollectionConfig, LogLevel
from app.models.request_context import RequestContext
from app.models.skill_meta import SkillMetaInfo
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.app_orchestrator import AppOrchestrator
from app.services.dynamic_path_composer import DynamicPathComposer
from app.services.log_center import LogCenter
from app.services.path_store import PathStore
from app.services.skill_meta_service import SkillMetaService

logger = logging.getLogger(__name__)

# Type alias for existing gateway handlers
GatewayHandler = Callable[..., Any]


class GatewayOrchestratorBridge:
    """Bridge between LightBrainGateway and the new AppOrchestrator.

    Responsibilities:
    1. Inject RequestContext into every call chain
    2. Route through AppOrchestrator → MessageBus → Workers
    3. Register legacy handlers as SimpleWorkers on the Bus
    4. Log all executions to LogCenter
    5. Fall back to old chain when new chain is unavailable
    """

    def __init__(
        self,
        bus: MessageBus | None = None,
        worker_manager: WorkerManager | None = None,
        log_center: LogCenter | None = None,
        meta_service: SkillMetaService | None = None,
        path_store: PathStore | None = None,
        universal_skill: Any = None,
        dynamic_composer: DynamicPathComposer | None = None,
    ) -> None:
        self._bus = bus
        self._worker_manager = worker_manager
        self._log_center = log_center
        self._meta_service = meta_service
        self._path_store = path_store or PathStore()
        self._universal_skill = universal_skill
        self._dynamic_composer = dynamic_composer
        self._orchestrators: dict[str, AppOrchestrator] = {}

    # -- RequestContext injection ---------------------------------------------

    def create_context(
        self,
        user_id: str,
        app_instance_id: str,
        caller_id: str = "gateway",
    ) -> RequestContext:
        """Create a root request context with full identity tracing."""
        return RequestContext.new_root(
            user_id=user_id,
            app_instance_id=app_instance_id,
            caller_id=caller_id,
        )

    # -- Orchestrator management ----------------------------------------------

    async def get_or_create_orchestrator(
        self,
        app_instance_id: str,
    ) -> AppOrchestrator | None:
        """Get or create an AppOrchestrator for the given app."""
        if not self._bus:
            return None

        if app_instance_id not in self._orchestrators:
            orch = AppOrchestrator(
                bus=self._bus,
                path_store=self._path_store,
                universal_skill=self._universal_skill,
                dynamic_composer=self._dynamic_composer,
            )
            await orch.init()
            self._orchestrators[app_instance_id] = orch
            logger.info(
                "Orchestrator created for app %s (%d paths loaded)",
                app_instance_id, len(orch._paths),
            )

        return self._orchestrators[app_instance_id]

    # -- Execution through the new chain --------------------------------------

    async def execute_command(
        self,
        user_id: str,
        app_instance_id: str,
        text: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Execute a command through the new chain.

        Returns a dict result on success, or None to signal the caller
        should fall back to the legacy handler chain.
        """
        if not self._bus:
            return None  # New chain not available

        ctx = self.create_context(user_id, app_instance_id)

        orch = await self.get_or_create_orchestrator(app_instance_id)
        if not orch:
            return None

        request = SkillExecutionRequest(
            skill_id="__gateway__",
            app_instance_id=app_instance_id,
            workflow_id="direct",
            step_id="text_input",
            inputs={"text": text},
            config=ctx.inject_into_config({"session_id": session_id}),
            user_id=user_id,
        )

        start_ms = time.monotonic()
        try:
            result = await orch.process(request)
            elapsed_ms = (time.monotonic() - start_ms) * 1000

            # Log to LogCenter
            self._log(
                ctx.trace_id, "orchestrator", app_instance_id, user_id,
                "INFO", f"processed in {elapsed_ms:.0f}ms",
                inputs={"text": text[:100]}, duration_ms=elapsed_ms,
            )

            # Convert to gateway-compatible response
            if result and result.status == "failed":
                # Orchestrator could not handle this request — signal fallback
                logger.debug(
                    "Orchestrator returned failed status: %s, falling back",
                    result.error or result.output,
                )
                return None

            if result and result.output:
                content = result.output.get("text", str(result.output)) if isinstance(result.output, dict) else str(result.output)
            else:
                content = str(result) if result else ""

            return {
                "type": "text",
                "content": content,
                "trace_id": ctx.trace_id,
                "status": result.status if result else "completed",
            }

        except Exception as e:
            elapsed_ms = (time.monotonic() - start_ms) * 1000
            logger.warning("Orchestrator failed (falling back): %s", e)
            self._log(
                ctx.trace_id, "orchestrator", app_instance_id, user_id,
                "ERROR", str(e), duration_ms=elapsed_ms,
            )
            return None  # Signal fallback

    # -- Direct skill invocation via MessageBus --------------------------------

    async def invoke_skill(
        self,
        user_id: str,
        app_instance_id: str,
        skill_id: str,
        inputs: dict[str, Any],
        action: str = "execute",
    ) -> dict[str, Any] | None:
        """Invoke a single skill directly through the MessageBus."""
        if not self._bus:
            return None

        ctx = self.create_context(user_id, app_instance_id, skill_id)

        start_ms = time.monotonic()
        try:
            result = await self._bus.call(
                skill_id=skill_id,
                action=action,
                request=ctx.inject_into_config(inputs),
                timeout=60,
            )
            elapsed_ms = (time.monotonic() - start_ms) * 1000

            self._log(
                ctx.trace_id, skill_id, app_instance_id, user_id,
                "INFO", f"{action} in {elapsed_ms:.0f}ms",
                inputs=inputs, outputs=result, duration_ms=elapsed_ms,
            )

            return {
                "type": "text",
                "content": result.get("result", str(result)) if isinstance(result, dict) else str(result),
                "trace_id": ctx.trace_id,
            }

        except Exception as e:
            elapsed_ms = (time.monotonic() - start_ms) * 1000
            logger.warning("Skill %s failed: %s", skill_id, e)
            self._log(
                ctx.trace_id, skill_id, app_instance_id, user_id,
                "ERROR", str(e), duration_ms=elapsed_ms,
            )
            return None

    # -- Register system skills as Workers ------------------------------------

    def register_system_skills(
        self,
        handlers: dict[str, GatewayHandler],
        meta_entries: dict[str, Any] | None = None,
    ) -> None:
        """Register existing system skill handlers as SimpleWorkers on the Bus.

        Bridges the old `handler(request) -> dict` model to the new
        async Worker model so existing skills run on the MessageBus
        without any code changes.
        """
        if not self._worker_manager or not self._bus:
            logger.debug("No worker_manager/bus — skipping registration")
            return

        for skill_id, handler in handlers.items():
            meta = None
            if meta_entries and skill_id in meta_entries:
                entry = meta_entries[skill_id]
                meta = SkillMetaInfo(
                    skill_id=skill_id,
                    name=entry.get("name", skill_id),
                    description=entry.get("description", ""),
                    input_schema=entry.get("input_schema"),
                    output_schema=entry.get("output_schema"),
                )

            worker = SimpleWorker(
                skill_id=skill_id,
                handler=handler,
                meta=meta,
            )
            self._worker_manager.register_and_start(worker)
            logger.info("Registered system skill as Worker: %s", skill_id)

            if self._meta_service and meta:
                self._meta_service.register(meta)

    # -- Register Gateway handlers as Workers -----------------------------------

    def register_gateway_handlers(
        self,
        gateway: Any,
        handler_names: list[str] | None = None,
    ) -> int:
        """Wrap Gateway's internal handlers and register them as Bus Workers.

        Each handler has signature: async def _handle_xxx(command, session_id, apps)
        We wrap it into an async dict -> dict callable compatible with SimpleWorker.
        """
        if not self._worker_manager or not self._bus:
            logger.debug("No worker_manager/bus — skipping gateway handler registration")
            return 0

        # Default handler set if none specified
        if handler_names is None:
            handler_names = [
                "greet", "list_apps", "query_status", "query_help",
                "create_app", "start_app", "stop_app",
                "pause_app", "resume_app", "query_app",
                "modify_app", "delete_app",
                "grant_admin", "grant_root", "revoke_role",
                "show_permissions", "list_users", "show_self",
            ]

        # Map intent to actual handler method name
        intent_map = {
            "greet": "_handle_greet",
            "list_apps": "_handle_list_apps",
            "query_status": "_handle_query_status",
            "query_help": "_handle_query_help",
            "create_app": "_handle_create_app",
            "start_app": "_handle_start_app",
            "stop_app": "_handle_stop_app",
            "pause_app": "_handle_pause_app",
            "resume_app": "_handle_resume_app",
            "query_app": "_handle_query_app",
            "modify_app": "_handle_modify_app",
            "delete_app": "_handle_delete_app",
            "grant_admin": "_handle_permission",
            "grant_root": "_handle_permission",
            "revoke_role": "_handle_permission",
            "show_permissions": "_handle_permission",
            "list_users": "_handle_permission",
            "show_self": "_handle_permission",
        }

        count = 0
        for intent in handler_names:
            method_name = intent_map.get(intent, f"_handle_{intent}")
            handler = getattr(gateway, method_name, None)
            if handler is None:
                logger.warning("Gateway handler not found for intent: %s (method: %s)", intent, method_name)
                continue

            # Create async wrapper using closure (captures handler + intent by value)
            def _make_wrapper(h, intent_name):
                async def wrapped(request: dict) -> dict:
                    from app.models.chat import InterpretedCommand
                    cmd = InterpretedCommand(
                        intent=intent_name,
                        raw_input=request.get("text", ""),
                        params=request.get("params", {}),
                        user_id=request.get("user_id", ""),
                    )
                    session_id = request.get("session_id", "default")
                    available_apps = request.get("available_apps", [])
                    result = await h(cmd, session_id, available_apps)
                    if hasattr(result, "model_dump"):
                        return result.model_dump(mode="json")
                    if isinstance(result, dict):
                        return result
                    return {"type": "text", "content": str(result)}
                return wrapped

            wrapped = _make_wrapper(handler, intent)

            meta = SkillMetaInfo(
                skill_id=intent,
                name=intent,
                description=f"Gateway handler: {intent}",
            )
            worker = SimpleWorker(
                skill_id=intent,
                handler=wrapped,
                meta=meta,
            )
            # Use sync register during bootstrap (message loop will start when event loop runs)
            self._worker_manager.register(worker)
            if self._meta_service:
                self._meta_service.register(meta)
            count += 1
            logger.info("Registered gateway handler as Worker: %s", intent)

        return count

    # -- App binding management -----------------------------------------------

    def bind_app(
        self,
        app_instance_id: str,
        skill_ids: list[str],
        *,
        log_level: LogLevel = "INFO",
        user_id: str = "",
    ) -> AppInstanceBinding:
        """Bind skills to an app instance with log config."""
        binding = AppInstanceBinding(
            app_instance_id=app_instance_id,
            log_config=LogCollectionConfig(level=log_level),
        )
        for sid in skill_ids:
            binding.bind_skill(sid)
        if self._log_center:
            self._log_center.set_app_config(app_instance_id, binding.log_config)
        return binding

    # -- Query helpers --------------------------------------------------------

    def is_available(self) -> bool:
        return self._bus is not None

    def get_available_skills(self) -> list[dict[str, Any]]:
        if not self._meta_service:
            return []
        return [s.summary() for s in self._meta_service.list_all()]

    # -- Internal logging -----------------------------------------------------

    def _log(
        self,
        trace_id: str,
        skill_id: str,
        app_instance_id: str,
        user_id: str,
        level: LogLevel,
        message: str,
        inputs: dict | None = None,
        outputs: dict | None = None,
        duration_ms: float | None = None,
    ) -> None:
        if not self._log_center:
            return
        self._log_center.log(
            trace_id=trace_id,
            skill_id=skill_id,
            action="execute",
            app_instance_id=app_instance_id,
            user_id=user_id,
            level=level,
            message=message,
            inputs=inputs,
            outputs=outputs,
            duration_ms=duration_ms,
        )
