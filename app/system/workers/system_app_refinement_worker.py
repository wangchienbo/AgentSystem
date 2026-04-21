"""System App Refinement Worker — wraps AppRefinementOrchestratorService as a MessageBus Worker.

Registers as 'system.app_refinement' on the MessageBus so Gateway can modify apps via RPC.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.message_bus import MessageBus
from app.core.skill_worker import SkillWorker
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.app_refinement import SuggestedSkillRefinementClosureRequest

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
            request = SuggestedSkillRefinementClosureRequest(
                blueprint_id=inputs.get("app_id", ""),
                name=inputs.get("name") or inputs.get("app_id", "refined-app"),
                goal=inputs.get("description", "refine app"),
                skill_ids=inputs.get("skill_ids", []),
                user_id=inputs.get("user_id", "system"),
                dry_run=True,
                install=False,
                run=False,
            )

            result = self._refinement.refine_closure(request)

            output = {
                "blueprint_id": None if result.blueprint is None else result.blueprint.id,
                "dry_run": True,
                "created_skills": [item.get("skill_id") if isinstance(item, dict) else getattr(item, "skill_id", None) for item in result.diagnostics],
                "modified_skills": list(result.reused_skill_ids),
            }
            output["created_skills"] = [item for item in output["created_skills"] if item]
            return self._success(output)
        except Exception as e:
            return self._error(f"Dry run failed: {str(e)}")

    def _handle_refine(self, inputs: dict) -> SkillExecutionResult:
        if not self._refinement:
            return self._error("AppRefinement service not available")

        try:
            request = SuggestedSkillRefinementClosureRequest(
                blueprint_id=inputs.get("app_id", ""),
                name=inputs.get("name") or inputs.get("app_id", "refined-app"),
                goal=inputs.get("description", "refine app"),
                skill_ids=inputs.get("skill_ids", []),
                user_id=inputs.get("user_id", "system"),
                dry_run=False,
                install=bool(inputs.get("install", False)),
                run=bool(inputs.get("run", False)),
                workflow_inputs=inputs.get("workflow_inputs", {}),
                trigger=inputs.get("trigger", "manual"),
                reviewer=inputs.get("reviewer", ""),
                version=inputs.get("version", "candidate-1"),
                note=inputs.get("note", "phase5 refined candidate"),
                target_app=inputs.get("target_app", ""),
                context_hints=inputs.get("context_hints", []),
                related_session_ids=inputs.get("related_session_ids", []),
            )

            result = self._refinement.refine_closure(request)

            output = {
                "blueprint_id": None if result.blueprint is None else result.blueprint.id,
                "dry_run": False,
                "created_skills": [item.skill_id for item in result.created_skills],
                "modified_skills": list(result.reused_skill_ids),
                "release_entry": result.release_entry,
                "install_result": result.install_result,
                "execution_result": result.execution_result,
                "diagnostics": result.diagnostics,
                "target_app": request.target_app,
                "context_hints": list(request.context_hints),
                "related_session_ids": list(request.related_session_ids),
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
