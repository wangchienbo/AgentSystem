from __future__ import annotations

from typing import Callable

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.skill_control import SkillRegistryEntry
from app.models.telemetry import StepTelemetryRecord
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryError, SchemaRegistryService
from app.services.model_client import ModelClientError
from app.services.telemetry_service import TelemetryService
from app.services.executable_skill_adapter import ExecutableSkillAdapter, ExecutableSkillAdapterError
from app.core.skill_invoker import (
    InvocationContext,
    SkillCycleError,
    SkillDepthLimitError,
    SkillInvoker,
    SkillInvocationError,
    create_invocation_context,
    get_invoker_from_request,
    get_context_from_request,
)

SkillHandler = Callable[[SkillExecutionRequest], SkillExecutionResult]


class SkillRuntimeError(ValueError):
    pass


class SkillContractViolationError(SkillRuntimeError):
    pass


class SkillRuntimeService:
    def __init__(
        self,
        store: RuntimeStateStore | None = None,
        schema_registry: SchemaRegistryService | None = None,
        telemetry_service: TelemetryService | None = None,
    ) -> None:
        self._handlers: dict[str, SkillHandler] = {}
        self._entries: dict[str, SkillRegistryEntry] = {}
        self._store = store
        self._schema_registry = schema_registry
        self._telemetry_service = telemetry_service
        self._executions: dict[str, SkillExecutionResult] = {}
        self._executable_adapter = ExecutableSkillAdapter()

    def register_handler(self, skill_id: str, handler: SkillHandler, entry: SkillRegistryEntry | None = None) -> None:
        self._handlers[skill_id] = handler
        if entry is not None:
            self._entries[skill_id] = entry

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        entry = self._entries.get(request.skill_id)
        adapter_kind = entry.runtime_adapter if entry is not None else "callable"
        if adapter_kind not in {"callable", "script", "executable"}:
            raise SkillRuntimeError(f"Unsupported skill runtime adapter: {adapter_kind}")
        if adapter_kind == "callable" and request.skill_id not in self._handlers:
            raise SkillRuntimeError(f"Skill handler not found: {request.skill_id}")

        # Phase F.10: Inject SkillInvoker for callable skills only
        # Script/executable skills run in subprocess and can't use the invoker
        enriched_request = self._enrich_invocation_context(request) if adapter_kind == "callable" else request

        try:
            self._validate_request_contract(enriched_request, entry)
            if adapter_kind in {"script", "executable"}:
                result = self._executable_adapter.execute(entry, enriched_request) if entry is not None else self._execute_script(enriched_request)
            else:
                result = self._handlers[enriched_request.skill_id](enriched_request)
            self._validate_result_contract(result, entry)
        except SkillContractViolationError as error:
            result = SkillExecutionResult(
                skill_id=enriched_request.skill_id,
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
                skill_id=enriched_request.skill_id,
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
        except ExecutableSkillAdapterError as error:
            result = SkillExecutionResult(
                skill_id=enriched_request.skill_id,
                status="failed",
                output={},
                error=str(error),
                error_detail={
                    "kind": "executable_adapter_error",
                    "subkind": error.kind,
                    "message": str(error),
                    "retryable": False,
                    **error.detail,
                },
            )
        except (SkillCycleError, SkillDepthLimitError):
            # Invocation guard exceptions must propagate up the call chain
            raise
        except Exception as error:  # noqa: BLE001
            result = SkillExecutionResult(
                skill_id=enriched_request.skill_id,
                status="failed",
                output={},
                error=str(error),
                error_detail={
                    "kind": "runtime_error",
                    "message": str(error),
                    "retryable": False,
                },
            )
        execution_key = f"{enriched_request.app_instance_id}:{enriched_request.workflow_id}:{enriched_request.step_id}:{enriched_request.skill_id}"
        self._executions[execution_key] = result
        self._persist()
        if self._telemetry_service is not None:
            self._telemetry_service.record_step(
                StepTelemetryRecord(
                    interaction_id=f"workflow:{enriched_request.app_instance_id}:{enriched_request.workflow_id}",
                    step_id=enriched_request.step_id,
                    step_type="skill",
                    name=enriched_request.skill_id,
                    success=result.status == "completed",
                    error_code=result.error_detail.get("kind") if result.error_detail else None,
                    payload_summary={"status": result.status},
                ),
                app_id=enriched_request.app_instance_id.split(":")[0] if enriched_request.app_instance_id else None,
            )
        return result

    def _enrich_invocation_context(self, request: SkillExecutionRequest) -> SkillExecutionRequest:
        """Inject SkillInvoker into request.config for callable skills.

        If the request already has an invoker (cross-skill call), pass it through.
        If not (top-level call), create a fresh InvocationContext + invoker.
        """
        existing_invoker = get_invoker_from_request(request)
        if existing_invoker is not None:
            # Already part of a call chain — pass through as-is
            return request

        # Top-level call — create fresh context and invoker
        ctx = create_invocation_context(request)
        invoker = SkillInvoker(self.execute, ctx)
        return SkillExecutionRequest(
            skill_id=request.skill_id,
            app_instance_id=request.app_instance_id,
            workflow_id=request.workflow_id,
            step_id=request.step_id,
            inputs=request.inputs,
            config={**request.config, "__invoker__": invoker, "__invocation_ctx__": ctx},
        )

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
