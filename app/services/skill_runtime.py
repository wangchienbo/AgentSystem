from __future__ import annotations

import json
import subprocess
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
        try:
            if adapter_kind == "script":
                result = self._execute_script(request)
            else:
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

    def _execute_script(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        entry = self._entries.get(request.skill_id)
        if entry is None or entry.manifest is None:
            raise SkillRuntimeError(f"Script adapter requires manifest entry: {request.skill_id}")
        command = entry.manifest.adapter.command
        if not command:
            raise SkillRuntimeError(f"Script adapter command missing: {request.skill_id}")
        payload = request.model_dump(mode="json")
        completed = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        if completed.returncode != 0:
            raise SkillRuntimeError(completed.stderr.strip() or f"Script adapter failed: {request.skill_id}")
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise SkillRuntimeError(f"Script adapter produced invalid JSON: {request.skill_id}") from error
        return SkillExecutionResult(**raw)

    def list_failures(self) -> list[SkillExecutionResult]:
        return [item for item in self._executions.values() if item.status == "failed"]

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("skill_executions", self._executions)
