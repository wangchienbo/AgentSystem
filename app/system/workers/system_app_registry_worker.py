"""System App Registry Worker — wraps AppRegistryService as a MessageBus Worker.

Registers as 'system.app_registry' on the MessageBus so Gateway and other components
can interact with app registration via RPC.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.message_bus import MessageBus
from app.core.skill_worker import SkillWorker
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult

logger = logging.getLogger(__name__)


class SystemAppRegistryWorker(SkillWorker):
    """MessageBus Worker wrapping AppRegistryService."""

    worker_id = "system.app_registry"

    def __init__(self, bus: MessageBus, registry_service: Any) -> None:
        self._bus = bus
        self._registry = registry_service

    async def init(self, config: dict[str, Any] | None = None) -> None:
        logger.info("SystemAppRegistryWorker registered")

    async def shutdown(self) -> None:
        pass

    async def process(self, request: Any) -> Any:
        if not isinstance(request, SkillExecutionRequest):
            return self._error("Expected SkillExecutionRequest")

        action = request.action
        inputs = request.inputs

        try:
            if action == "list":
                return self._handle_list(inputs)
            elif action == "get":
                return self._handle_get(inputs)
            elif action == "register_blueprint":
                return self._handle_register_blueprint(inputs)
            elif action == "get_by_owner":
                return self._handle_get_by_owner(inputs)
            else:
                return self._error(f"Unknown action: {action}")
        except Exception as e:
            logger.exception("AppRegistry RPC error: %s", e)
            return self._error(str(e))

    def _handle_list(self, inputs: dict) -> SkillExecutionResult:
        if self._registry:
            try:
                entries = self._registry.list_entries()
                data = [
                    {
                        "app_id": e.app_id,
                        "status": e.status,
                        "owner_user_id": e.owner_user_id,
                    }
                    for e in entries
                ]
                return self._success({"entries": data, "count": len(data)})
            except Exception as e:
                return self._error(str(e))
        return self._error("AppRegistry service not available")

    def _handle_get(self, inputs: dict) -> SkillExecutionResult:
        app_id = inputs.get("app_id", "")
        if self._registry:
            try:
                entry = self._registry.get_entry(app_id)
                if entry:
                    return self._success({
                        "app_id": entry.app_id,
                        "status": entry.status,
                        "owner_user_id": entry.owner_user_id,
                    })
                return self._success({"app_id": app_id, "status": None, "found": False})
            except Exception as e:
                return self._success({"app_id": app_id, "status": None, "found": False, "error": str(e)})
        return self._error("AppRegistry service not available")

    def _handle_register_blueprint(self, inputs: dict) -> SkillExecutionResult:
        if self._registry:
            try:
                from app.models.app_blueprint import AppBlueprint
                bp_data = inputs.get("blueprint", {})
                description = inputs.get("description", "")
                if bp_data:
                    bp = AppBlueprint.model_validate(bp_data)
                    self._registry.register_blueprint(bp, description=description)
                    return self._success({"app_id": bp.app_id, "status": "registered"})
            except Exception as e:
                return self._error(str(e))
        return self._error("AppRegistry service not available")

    def _handle_get_by_owner(self, inputs: dict) -> SkillExecutionResult:
        owner_id = inputs.get("owner_user_id", "")
        if self._registry:
            try:
                entries = self._registry.list_entries()
                # Filter: owner's apps + system apps
                data = [
                    {
                        "app_id": e.app_id,
                        "status": e.status,
                        "owner_user_id": e.owner_user_id,
                    }
                    for e in entries
                    if e.owner_user_id == owner_id or e.owner_user_id == "system"
                ]
                return self._success({"entries": data, "count": len(data)})
            except Exception as e:
                return self._error(str(e))
        return self._error("AppRegistry service not available")

    @staticmethod
    def _success(data: dict) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.app_registry",
            status="completed",
            output=data,
        )

    @staticmethod
    def _error(message: str) -> SkillExecutionResult:
        return SkillExecutionResult(
            skill_id="system.app_registry",
            status="failed",
            output={},
            error=message,
        )
