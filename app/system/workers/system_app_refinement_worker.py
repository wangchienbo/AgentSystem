"""System App Refinement Worker — wraps AppRefinementOrchestratorService as a MessageBus Worker.

Registers as 'system.app_refinement' on the MessageBus so Gateway can modify apps via RPC.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.message_bus import MessageBus
from app.core.skill_worker import SkillWorker
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult

logger = logging.getLogger(__name__)


class SystemAppRefinementWorker(SkillWorker):
    """MessageBus Worker wrapping AppRefinementOrchestratorService."""

    worker_id = "system.app_refinement"

    def __init__(self, bus: MessageBus, refinement_service: Any) -> None:
        self._bus = bus
        self._refinement = refinement_service

    async def init(self, config: dict[str, Any] | None = None) -> None:
        logger.info("SystemAppRefinementWorker registered")

    async def shutdown(self) -> None:
        pass

    async def process(self, request: Any) -> Any:
        if not isinstance(request, SkillExecutionRequest):
            return self._error("Expected SkillExecutionRequest")

        action = request.action
        inputs = request.inputs

        try:
            if action == "dry_run":
                return self._handle_dry_run(inputs)
            elif action == "refine":
                return self._handle_refine(inputs)
            else:
                return self._error(f"Unknown action: {action}")
        except Exception as e:
            logger.exception("AppRefinement RPC error: %s", e)
            return self._error(str(e))

    def _handle_dry_run(self, inputs: dict) -> SkillExecutionResult:
        if not self._refinement:
            return self._error("AppRefinement service not available")

        try:
            from app.models.app_refinement import AppRefinementRequest

            request = AppRefinementRequest(
                app_id=inputs.get("app_id", ""),
                description=inputs.get("description", ""),
                new_features=inputs.get("new_features", []),
                user_id=inputs.get("user_id", "system"),
                dry_run=True,
            )

            result = self._refinement.refine_closure(request)

            output = {
                "app_id": result.app_id if hasattr(result, 'app_id') else inputs.get("app_id"),
                "dry_run": True,
                "created_skills": result.created_skill_ids if hasattr(result, 'created_skill_ids') else [],
                "modified_skills": result.modified_skill_ids if hasattr(result, 'modified_skill_ids') else [],
            }
            return self._success(output)
        except Exception as e:
            return self._error(f"Dry run failed: {str(e)}")

    def _handle_refine(self, inputs: dict) -> SkillExecutionResult:
        if not self._refinement:
            return self._error("AppRefinement service not available")

        try:
            from app.models.app_refinement import AppRefinementRequest

            request = AppRefinementRequest(
                app_id=inputs.get("app_id", ""),
                description=inputs.get("description", ""),
                new_features=inputs.get("new_features", []),
                user_id=inputs.get("user_id", "system"),
                dry_run=False,
            )

            result = self._refinement.refine_closure(request)

            output = {
                "app_id": result.app_id if hasattr(result, 'app_id') else inputs.get("app_id"),
                "dry_run": False,
                "created_skills": result.created_skill_ids if hasattr(result, 'created_skill_ids') else [],
                "modified_skills": result.modified_skill_ids if hasattr(result, 'modified_skill_ids') else [],
            }
            return self._success(output)
        except Exception as e:
            return self._error(f"Refinement failed: {str(e)}")

    @staticmethod
    def _success(data: dict) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.app_refinement",
            status="completed",
            output=data,
        )

    @staticmethod
    def _error(message: str) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.app_refinement",
            status="failed",
            output={},
            error=message,
        )
