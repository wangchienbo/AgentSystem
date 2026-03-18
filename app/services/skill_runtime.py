from __future__ import annotations

from typing import Callable

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.skill_control import SkillRegistryEntry
from app.services.runtime_state_store import RuntimeStateStore

SkillHandler = Callable[[SkillExecutionRequest], SkillExecutionResult]


class SkillRuntimeError(ValueError):
    pass


class SkillRuntimeService:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._handlers: dict[str, SkillHandler] = {}
        self._entries: dict[str, SkillRegistryEntry] = {}
        self._store = store
        self._executions: dict[str, SkillExecutionResult] = {}

    def register_handler(self, skill_id: str, handler: SkillHandler, entry: SkillRegistryEntry | None = None) -> None:
        self._handlers[skill_id] = handler
        if entry is not None:
            self._entries[skill_id] = entry

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        if request.skill_id not in self._handlers:
            raise SkillRuntimeError(f"Skill handler not found: {request.skill_id}")
        adapter_kind = self._entries.get(request.skill_id).runtime_adapter if request.skill_id in self._entries else "callable"
        if adapter_kind not in {"callable", "script"}:
            raise SkillRuntimeError(f"Unsupported skill runtime adapter: {adapter_kind}")
        if adapter_kind == "script":
            raise SkillRuntimeError(f"Script adapter not implemented yet: {request.skill_id}")
        try:
            result = self._handlers[request.skill_id](request)
        except Exception as error:  # noqa: BLE001
            result = SkillExecutionResult(
                skill_id=request.skill_id,
                status="failed",
                output={},
                error=str(error),
            )
        execution_key = f"{request.app_instance_id}:{request.workflow_id}:{request.step_id}:{request.skill_id}"
        self._executions[execution_key] = result
        self._persist()
        return result

    def list_executions(self) -> list[SkillExecutionResult]:
        return list(self._executions.values())

    def list_failures(self) -> list[SkillExecutionResult]:
        return [item for item in self._executions.values() if item.status == "failed"]

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("skill_executions", self._executions)
