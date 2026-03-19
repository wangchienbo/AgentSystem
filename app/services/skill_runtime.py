from __future__ import annotations

import json
import subprocess
from typing import Callable

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.skill_control import SkillRegistryEntry
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryError, SchemaRegistryService
from app.services.model_client import ModelClientError

SkillHandler = Callable[[SkillExecutionRequest], SkillExecutionResult]


class SkillRuntimeError(ValueError):
    pass


class SkillContractViolationError(SkillRuntimeError):
    pass


class SkillRuntimeService:
    def __init__(self, store: RuntimeStateStore | None = None, schema_registry: SchemaRegistryService | None = None) -> None:
        self._handlers: dict[str, SkillHandler] = {}
        self._entries: dict[str, SkillRegistryEntry] = {}
        self._store = store
        self._schema_registry = schema_registry
        self._executions: dict[str, SkillExecutionResult] = {}

    def register_handler(self, skill_id: str, handler: SkillHandler, entry: SkillRegistryEntry | None = None) -> None:
        self._handlers[skill_id] = handler
        if entry is not None:
            self._entries[skill_id] = entry

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        if request.skill_id not in self._handlers:
            raise SkillRuntimeError(f"Skill handler not found: {request.skill_id}")
        entry = self._entries.get(request.skill_id)
        adapter_kind = entry.runtime_adapter if entry is not None else "callable"
        if adapter_kind not in {"callable", "script"}:
            raise SkillRuntimeError(f"Unsupported skill runtime adapter: {adapter_kind}")
        try:
            self._validate_request_contract(request, entry)
            if adapter_kind == "script":
                result = self._execute_script(request)
            else:
                result = self._handlers[request.skill_id](request)
            self._validate_result_contract(result, entry)
        except SkillContractViolationError as error:
            result = SkillExecutionResult(
                skill_id=request.skill_id,
                status="failed",
                output={},
                error=f"contract violation: {error}",
                error_detail={
                    "kind": "contract_violation",
                    "message": str(error),
                    "retryable": False,
                },
            )
        except ModelClientError as error:
            result = SkillExecutionResult(
                skill_id=request.skill_id,
                status="failed",
                output={},
                error=str(error),
                error_detail={
                    "kind": "model_client_error",
                    "message": str(error),
                    "retryable": error.retryable,
                    "status_code": error.status_code,
                },
            )
        except Exception as error:  # noqa: BLE001
            result = SkillExecutionResult(
                skill_id=request.skill_id,
                status="failed",
                output={},
                error=str(error),
                error_detail={
                    "kind": "runtime_error",
                    "message": str(error),
                    "retryable": False,
                },
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

    def _validate_request_contract(self, request: SkillExecutionRequest, entry: SkillRegistryEntry | None) -> None:
        if self._schema_registry is None or entry is None or entry.manifest is None:
            return
        schema_ref = entry.manifest.contract.input_schema_ref
        if not schema_ref:
            return
        try:
            self._schema_registry.validate(schema_ref, request.inputs)
        except SchemaRegistryError as error:
            raise SkillContractViolationError(f"input contract failed for {request.skill_id}: {error}") from error

    def _validate_result_contract(self, result: SkillExecutionResult, entry: SkillRegistryEntry | None) -> None:
        if self._schema_registry is None or entry is None or entry.manifest is None:
            return
        contract = entry.manifest.contract
        if result.status == "completed" and contract.output_schema_ref:
            try:
                self._schema_registry.validate(contract.output_schema_ref, result.output)
            except SchemaRegistryError as error:
                raise SkillContractViolationError(f"output contract failed for {result.skill_id}: {error}") from error
        if result.status == "failed" and contract.error_schema_ref:
            try:
                self._schema_registry.validate(contract.error_schema_ref, {"message": result.error})
            except SchemaRegistryError as error:
                raise SkillContractViolationError(f"error contract failed for {result.skill_id}: {error}") from error

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("skill_executions", self._executions)
