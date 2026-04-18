"""System Meta App Worker — wraps MetaAppCreationOrchestrator as a MessageBus Worker.

Registers as 'system.meta_app' on the MessageBus so Gateway can create apps via RPC.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.message_bus import MessageBus
from app.core.skill_worker import SkillWorker
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult

logger = logging.getLogger(__name__)


class SystemMetaAppWorker(SkillWorker):
    """MessageBus Worker wrapping MetaAppCreationOrchestrator."""

    worker_id = "system.meta_app"

    def __init__(self, bus: MessageBus, orchestrator: Any) -> None:
        self._bus = bus
        self._orchestrator = orchestrator

    async def init(self, config: dict[str, Any] | None = None) -> None:
        logger.info("SystemMetaAppWorker registered")

    async def shutdown(self) -> None:
        pass

    async def process(self, request: Any) -> Any:
        if not isinstance(request, SkillExecutionRequest):
            return self._error("Expected SkillExecutionRequest")

        action = request.action
        inputs = request.inputs

        try:
            if action == "create_app":
                return await self._handle_create_app(inputs)
            else:
                return self._error(f"Unknown action: {action}")
        except Exception as e:
            logger.exception("MetaApp RPC error: %s", e)
            return self._error(str(e))

    async def _handle_create_app(self, inputs: dict) -> SkillExecutionResult:
        if not self._orchestrator:
            return self._error("MetaApp orchestrator not available")

        try:
            from app.models.app_meta_app import AppCreationFromMetaAppRequest

            app_name = inputs.get("app_name", "")
            app_goal = inputs.get("app_goal", "")
            app_type = inputs.get("app_type", "")
            complexity = inputs.get("complexity", "moderate")
            user_id = inputs.get("user_id", "system")
            features = inputs.get("features", [])
            constraints = inputs.get("constraints", [])

            request = AppCreationFromMetaAppRequest(
                app_name=app_name,
                goal=app_goal or f"创建一个{app_type}类型的 App：{app_name}",
                app_kind="service",
                complexity=complexity,
                user_id=user_id,
                scope={"app_type": app_type, "features": features, "constraints": constraints},
                context=inputs.get("context", ""),
                workflow_inputs=inputs.get("workflow_inputs", {}),
            )

            result = self._orchestrator.create_app_through_meta_app(request)

            output = {
                "app_id": result.installed_app.id if result.installed_app else None,
                "status": result.installed_app.status if result.installed_app else None,
                "created_skill_ids": result.created_skill_ids,
                "blueprint_id": result.blueprint.app_id if result.blueprint else None,
                "owner_user_id": result.installed_app.owner_user_id if result.installed_app else None,
            }
            return self._success(output)
        except Exception as e:
            return self._error(f"App creation failed: {str(e)}")

    @staticmethod
    def _success(data: dict) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.meta_app",
            status="completed",
            output=data,
        )

    @staticmethod
    def _error(message: str) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.meta_app",
            status="failed",
            output={},
            error=message,
        )
