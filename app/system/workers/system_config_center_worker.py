"""System Config Center Worker — wraps ConfigCenterService as a MessageBus Worker.

Registers as 'system.config_center' on the MessageBus so Gateway and other components
can manage skill template configs and app-skill bindings via RPC.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.message_bus import MessageBus
from app.core.skill_worker import SkillWorker
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult

logger = logging.getLogger(__name__)


class SystemConfigCenterWorker(SkillWorker):
    """MessageBus Worker wrapping ConfigCenterService."""

    worker_id = "system.config_center"

    def __init__(self, bus: MessageBus, config_center: Any) -> None:
        self._bus = bus
        self._config_center = config_center

    async def init(self, config: dict[str, Any] | None = None) -> None:
        logger.info("SystemConfigCenterWorker registered")

    async def shutdown(self) -> None:
        pass

    async def process(self, request: Any) -> Any:
        if not isinstance(request, SkillExecutionRequest):
            return self._error("Expected SkillExecutionRequest")

        action = request.action
        inputs = request.inputs

        try:
            if action == "set_skill_config":
                return self._handle_set_skill_config(inputs)
            elif action == "get_skill_config":
                return self._handle_get_skill_config(inputs)
            elif action == "list_skill_configs":
                return self._handle_list_skill_configs(inputs)
            elif action == "delete_skill_config":
                return self._handle_delete_skill_config(inputs)
            elif action == "set_app_skill_binding":
                return self._handle_set_app_skill_binding(inputs)
            elif action == "get_app_skill_binding":
                return self._handle_get_app_skill_binding(inputs)
            elif action == "get_app_bindings":
                return self._handle_get_app_bindings(inputs)
            elif action == "delete_app_skill_binding":
                return self._handle_delete_app_skill_binding(inputs)
            elif action == "resolve_model_preference":
                return self._handle_resolve_model_preference(inputs)
            elif action == "resolve_all_app_skills":
                return self._handle_resolve_all_app_skills(inputs)
            else:
                return self._error(f"Unknown action: {action}")
        except Exception as e:
            logger.exception("ConfigCenter RPC error: %s", e)
            return self._error(str(e))

    def _handle_set_skill_config(self, inputs: dict) -> SkillExecutionResult:
        skill_id = inputs.get("skill_id", "")
        if not skill_id:
            return self._error("skill_id is required")
        config = self._config_center.set_skill_config(
            skill_id=skill_id,
            model_preference=inputs.get("model_preference"),
            description=inputs.get("description", ""),
            metadata=inputs.get("metadata"),
        )
        return self._success({
            "skill_id": config.skill_id,
            "model_preference": config.model_preference,
        })

    def _handle_get_skill_config(self, inputs: dict) -> SkillExecutionResult:
        skill_id = inputs.get("skill_id", "")
        config = self._config_center.get_skill_config(skill_id)
        if config:
            return self._success({
                "skill_id": config.skill_id,
                "model_preference": config.model_preference,
                "description": config.description,
                "metadata": config.metadata,
            })
        return self._success({"skill_id": skill_id, "found": False})

    def _handle_list_skill_configs(self, inputs: dict) -> SkillExecutionResult:
        configs = self._config_center.list_skill_configs()
        data = [
            {
                "skill_id": c.skill_id,
                "model_preference": c.model_preference,
                "description": c.description,
            }
            for c in configs
        ]
        return self._success({"configs": data, "count": len(data)})

    def _handle_delete_skill_config(self, inputs: dict) -> SkillExecutionResult:
        skill_id = inputs.get("skill_id", "")
        deleted = self._config_center.delete_skill_config(skill_id)
        return self._success({"skill_id": skill_id, "deleted": deleted})

    def _handle_set_app_skill_binding(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        skill_id = inputs.get("skill_id", "")
        if not app_id or not skill_id:
            return self._error("app_id and skill_id are required")
        binding = self._config_center.set_app_skill_binding(
            app_id=app_id,
            skill_id=skill_id,
            model_preference=inputs.get("model_preference"),
            enabled=inputs.get("enabled", True),
            metadata=inputs.get("metadata"),
        )
        return self._success({
            "app_id": binding.app_id,
            "skill_id": binding.skill_id,
            "model_preference": binding.model_preference,
        })

    def _handle_get_app_skill_binding(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        skill_id = inputs.get("skill_id", "")
        binding = self._config_center.get_app_skill_binding(app_id, skill_id)
        if binding:
            return self._success({
                "app_id": binding.app_id,
                "skill_id": binding.skill_id,
                "model_preference": binding.model_preference,
                "enabled": binding.enabled,
            })
        return self._success({"app_id": app_id, "skill_id": skill_id, "found": False})

    def _handle_get_app_bindings(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        bindings = self._config_center.get_app_bindings(app_id)
        data = [
            {
                "skill_id": b.skill_id,
                "model_preference": b.model_preference,
                "enabled": b.enabled,
            }
            for b in bindings
        ]
        return self._success({"bindings": data, "count": len(data)})

    def _handle_delete_app_skill_binding(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        skill_id = inputs.get("skill_id", "")
        deleted = self._config_center.delete_app_skill_binding(app_id, skill_id)
        return self._success({"app_id": app_id, "skill_id": skill_id, "deleted": deleted})

    def _handle_resolve_model_preference(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id")
        skill_id = inputs.get("skill_id")
        resolved = self._config_center.resolve_model_preference(app_id, skill_id)
        return self._success({
            "app_id": app_id,
            "skill_id": skill_id,
            "model_preference": resolved,
        })

    def _handle_resolve_all_app_skills(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        skill_ids = inputs.get("skill_ids", [])
        resolved = self._config_center.resolve_all_app_skills(app_id, skill_ids)
        return self._success({
            "app_id": app_id,
            "resolved": resolved,
        })

    @staticmethod
    def _success(data: dict) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.config_center",
            status="completed",
            output=data,
        )

    @staticmethod
    def _error(message: str) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.config_center",
            status="failed",
            output={},
            error=message,
        )
