"""Gateway ↔ Orchestrator Bridge.

Central integration layer connecting LightBrainGateway to the new
G.1/G.2 module chain: AppOrchestrator → MessageBus → Skill Workers → LogCenter.

This is the bridge that makes the full execution chain work:
  User → Gateway → Bridge → Orchestrator → Bus → Workers → LogCenter

Main bridge for the orchestrated path. Bridge-first for app commands, with None reserved for local gateway fallback during migration.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.core.message_bus import MessageBus
from app.core.worker_manager import WorkerManager
from app.models.app_binding import AppInstanceBinding
from app.models.log_center import LogCollectionConfig, LogLevel
from app.models.request_context import RequestContext
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.app_orchestrator import AppOrchestrator
from app.services.dynamic_path_composer import DynamicPathComposer
from app.services.log_center import LogCenter
from app.services.path_store import PathStore
from app.services.skill_meta_service import SkillMetaService

logger = logging.getLogger(__name__)


class GatewayOrchestratorBridge:
    """Bridge between LightBrainGateway and the new AppOrchestrator.

    Responsibilities:
    1. Inject RequestContext into every call chain
    2. Route through AppOrchestrator → MessageBus → Workers
    3. Log all executions to LogCenter
    4. Use None only to signal fallback back into the local gateway app-command path
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

        Returns a dict result on success.
        Returns None only when the app-command bridge should fall back to the local gateway path.
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
                # Temporary degraded signal while old gateway routing still exists
                logger.debug(
                    "Orchestrator returned failed status: %s",
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
            logger.warning("Orchestrator failed: %s", e)
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
        meta_entries: dict[str, Any] | None = None,
    ) -> None:
        """Register skill metadata for orchestrator-facing intents."""
        if not self._meta_service or not meta_entries:
            return

        for skill_id, entry in meta_entries.items():
            from app.models.skill_meta import SkillMetaInfo
            meta = SkillMetaInfo(
                skill_id=skill_id,
                name=entry.get("name", skill_id),
                description=entry.get("description", ""),
                input_schema=entry.get("input_schema"),
                output_schema=entry.get("output_schema"),
            )
            self._meta_service.register(meta)

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
