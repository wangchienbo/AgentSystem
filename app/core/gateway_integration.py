"""Gateway Integration — connects LightBrainGateway to the new App Orchestrator architecture.

This is the bridge layer that wires together:
- Gateway → AppOrchestrator → MessageBus → Skill Workers → LogCenter

Primary gateway-to-orchestrator bridge. Legacy fallback behavior remains only until the direct orchestrator path is fully removed upstream.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.message_bus import MessageBus
from app.core.worker_manager import WorkerManager
from app.models.app_binding import AppInstanceBinding, SkillBindingConfig
from app.models.request_context import RequestContext
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.app_orchestrator import AppOrchestrator
from app.services.log_center import LogCenter
from app.services.skill_meta_service import SkillMetaService
from app.services.system_skill_registry import register_builtin_handlers
from app.core.skill_worker import SkillWorker

logger = logging.getLogger(__name__)


class GatewayIntegration:
    """Bridge between the Gateway and the new Orchestrator architecture.

    Responsibilities:
    1. Create RequestContext for each user request
    2. Route commands through the AppOrchestrator
    3. Keep degraded returns only for app-command intents that still need local fallback during migration
    4. Provide skill discovery metadata for the Gateway
    """

    def __init__(
        self,
        orchestrator: AppOrchestrator | None = None,
        message_bus: MessageBus | None = None,
        worker_manager: WorkerManager | None = None,
        log_center: LogCenter | None = None,
        skill_meta_service: SkillMetaService | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._bus = message_bus
        self._worker_manager = worker_manager
        self._log_center = log_center
        self._meta_service = skill_meta_service
        # Track per-user default app instance for stateless requests
        self._user_default_app: dict[str, str] = {}

    # -- RequestContext injection ---------------------------------------------

    def create_request_context(
        self,
        user_id: str,
        app_instance_id: str,
        caller_id: str = "user",
    ) -> RequestContext:
        """Create a new root RequestContext for a user request."""
        ctx = RequestContext.new_root(
            user_id=user_id,
            app_instance_id=app_instance_id,
            caller_id=caller_id,
        )
        # Ensure app has log config
        if self._log_center:
            config = self._log_center.get_app_config(app_instance_id)
        return ctx

    # -- Orchestrated execution -----------------------------------------------

    async def execute_via_orchestrator(
        self,
        user_id: str,
        app_instance_id: str,
        text: str,
        *,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a command through the new AppOrchestrator.

        Returns the same format the Gateway expects.
        Returns None only when an app-command bridge handoff must fall back to the local gateway path.
        """
        if not self._orchestrator:
            logger.debug("No orchestrator — skipping")
            return None

        ctx = self.create_request_context(
            user_id=user_id,
            app_instance_id=app_instance_id,
        )

        try:
            result = await self._orchestrator.execute_text_command(
                app_instance_id=app_instance_id,
                user_input=text,
                config=config or {},
            )

            # Log the execution
            self._log_execution(
                trace_id=ctx.trace_id,
                app_instance_id=app_instance_id,
                user_id=user_id,
                skill_id="orchestrator",
                status="completed" if result.get("status") == "success" else "failed",
                duration_ms=result.get("duration_ms", 0),
            )

            return {
                "type": "text",
                "content": result.get("output", result.get("result", "")),
                "trace_id": ctx.trace_id,
                "status": result.get("status", "unknown"),
            }

        except Exception as e:
            logger.warning("Orchestrator execution failed: %s", e)
            self._log_execution(
                trace_id=ctx.trace_id,
                app_instance_id=app_instance_id,
                user_id=user_id,
                skill_id="orchestrator",
                status="failed",
                duration_ms=0,
                error=str(e),
            )
            return None

    # -- Direct skill invocation (for single-skill commands) -------------------

    async def execute_skill_directly(
        self,
        user_id: str,
        app_instance_id: str,
        skill_id: str,
        inputs: dict[str, Any],
        action: str = "execute",
    ) -> dict[str, Any] | None:
        """Execute a single skill through the MessageBus.

        Returns None if the skill isn't registered as a Worker.
        """
        if not self._bus:
            return None

        ctx = self.create_request_context(
            user_id=user_id,
            app_instance_id=app_instance_id,
            caller_id=skill_id,
        )

        request = SkillExecutionRequest(
            skill_id=skill_id,
            app_instance_id=app_instance_id,
            workflow_id="direct",
            step_id=skill_id,
            inputs=inputs,
            config=ctx.inject_into_config({}),
            action=action,
            user_id=user_id,
        )

        start = datetime.now(UTC)
        try:
            result = await self._bus.call(
                skill_id=skill_id,
                action=action,
                request=request.model_dump(),
                timeout=30,
            )

            duration_ms = (datetime.now(UTC) - start).total_seconds() * 1000
            self._log_execution(
                trace_id=ctx.trace_id,
                app_instance_id=app_instance_id,
                user_id=user_id,
                skill_id=skill_id,
                status="completed",
                duration_ms=duration_ms,
            )

            return {
                "type": "text",
                "content": result.get("result", str(result)),
                "trace_id": ctx.trace_id,
            }

        except Exception as e:
            logger.warning("Direct skill execution failed: %s", e)
            return None

    # -- Skill discovery ------------------------------------------------------

    def get_available_skills(self) -> list[dict[str, Any]]:
        """Get list of registered skills for context injection."""
        if not self._meta_service:
            return []
        skills = self._meta_service.list_all()
        return [s.summary() for s in skills]

    def get_app_binding(self, app_instance_id: str) -> AppInstanceBinding | None:
        """Get the binding config for an app instance."""
        if not self._orchestrator:
            return None
        return self._orchestrator.get_app_binding(app_instance_id)

    # -- Logging --------------------------------------------------------------

    def _log_execution(
        self,
        trace_id: str,
        app_instance_id: str,
        user_id: str,
        skill_id: str,
        status: str,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        if not self._log_center:
            return
        self._log_center.log_execution(
            trace_id=trace_id,
            skill_id=skill_id,
            action="execute",
            app_instance_id=app_instance_id,
            user_id=user_id,
            status=status,
            duration_ms=duration_ms,
            error=error,
        )
