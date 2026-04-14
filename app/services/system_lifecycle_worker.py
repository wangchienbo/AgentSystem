"""System Lifecycle Worker — wraps AppLifecycleService as a MessageBus Worker.

Registers as 'system.lifecycle' on the MessageBus so Gateway and other components
can interact with app lifecycle (start/stop/pause/resume/register) via RPC.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.message_bus import MessageBus
from app.core.skill_worker import SkillWorker
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult

logger = logging.getLogger(__name__)


class SystemLifecycleWorker(SkillWorker):
    """MessageBus Worker wrapping AppLifecycleService."""

    worker_id = "system.lifecycle"

    def __init__(self, bus: MessageBus, lifecycle_service: Any) -> None:
        self._bus = bus
        self._lifecycle = lifecycle_service

    async def init(self, config: dict[str, Any] | None = None) -> None:
        logger.info("SystemLifecycleWorker registered")

    async def shutdown(self) -> None:
        pass

    async def process(self, request: Any) -> Any:
        if not isinstance(request, SkillExecutionRequest):
            return self._error("Expected SkillExecutionRequest")

        action = request.action
        inputs = request.inputs

        try:
            if action == "start":
                return self._handle_start(inputs)
            elif action == "stop":
                return self._handle_stop(inputs)
            elif action == "pause":
                return self._handle_pause(inputs)
            elif action == "resume":
                return self._handle_resume(inputs)
            elif action == "get_instance":
                return self._handle_get_instance(inputs)
            elif action == "register_instance":
                return self._handle_register_instance(inputs)
            elif action == "list_instances":
                return self._handle_list_instances(inputs)
            else:
                return self._error(f"Unknown action: {action}")
        except Exception as e:
            logger.exception("Lifecycle RPC error: %s", e)
            return self._error(str(e))

    def _handle_start(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        reason = inputs.get("reason", "rpc")
        if self._lifecycle:
            self._lifecycle.start(app_id, reason=reason)
            return self._success({"app_id": app_id, "status": "started", "reason": reason})
        return self._error("Lifecycle service not available")

    def _handle_stop(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        reason = inputs.get("reason", "rpc")
        if self._lifecycle:
            self._lifecycle.stop(app_id, reason=reason)
            return self._success({"app_id": app_id, "status": "stopped", "reason": reason})
        return self._error("Lifecycle service not available")

    def _handle_pause(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        reason = inputs.get("reason", "rpc")
        if self._lifecycle:
            self._lifecycle.pause(app_id, reason=reason)
            return self._success({"app_id": app_id, "status": "paused", "reason": reason})
        return self._error("Lifecycle service not available")

    def _handle_resume(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        reason = inputs.get("reason", "rpc")
        if self._lifecycle:
            self._lifecycle.resume(app_id, reason=reason)
            return self._success({"app_id": app_id, "status": "resumed", "reason": reason})
        return self._error("Lifecycle service not available")

    def _handle_get_instance(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        if self._lifecycle:
            try:
                instance = self._lifecycle.get_instance(app_id)
                data = {
                    "app_id": app_id,
                    "status": instance.status if instance else None,
                    "owner_user_id": instance.owner_user_id if instance else None,
                    "system_skills": list(instance.system_skills) if instance else [],
                    "resolved_skills": list(instance.resolved_skills) if instance else [],
                }
                return self._success(data)
            except Exception as e:
                return self._success({"app_id": app_id, "status": None, "error": str(e)})
        return self._error("Lifecycle service not available")

    def _handle_register_instance(self, inputs: dict) -> SkillExecutionResult:
        if self._lifecycle:
            # Accept serialized instance data and reconstruct
            from app.models.app_instance import AppInstance
            instance_data = inputs.get("instance", {})
            if instance_data:
                instance = AppInstance.model_validate(instance_data)
                self._lifecycle.register_instance(instance)
                return self._success({"app_id": instance.id, "status": "registered"})
        return self._error("Lifecycle service not available or missing instance data")

    def _handle_list_instances(self, inputs: dict) -> SkillExecutionResult:
        if self._lifecycle:
            try:
                instances = self._lifecycle.list_instances()
                data = [
                    {
                        "app_id": inst.id,
                        "status": inst.status,
                        "owner_user_id": inst.owner_user_id,
                    }
                    for inst in instances
                ]
                return self._success({"instances": data, "count": len(data)})
            except Exception as e:
                return self._error(str(e))
        return self._error("Lifecycle service not available")

    @staticmethod
    def _success(data: dict) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.lifecycle",
            status="completed",
            output=data,
        )

    @staticmethod
    def _error(message: str) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.lifecycle",
            status="failed",
            output={},
            error=message,
        )
