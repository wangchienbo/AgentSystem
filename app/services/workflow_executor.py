from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from copy import deepcopy

from app.models.workflow_execution import WorkflowExecutionResult, WorkflowRetryComparison, WorkflowStepExecution
from app.models.telemetry import StepTelemetryRecord, VersionBindingRecord
from app.services.runtime_state_store import RuntimeStateStore
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.lifecycle import AppLifecycleService
from app.services.skill_runtime import SkillRuntimeError, SkillRuntimeService
from app.models.skill_runtime import SkillExecutionRequest
from app.services.context_compaction import ContextCompactionService
from app.services.telemetry_service import TelemetryService


class WorkflowExecutorError(ValueError):
    pass


class WorkflowExecutorService:
    def __init__(
        self,
        registry: AppRegistryService,
        lifecycle: AppLifecycleService,
        data_store: AppDataStore,
        event_bus: EventBusService,
        context_store: AppContextStore | None = None,
        skill_runtime: SkillRuntimeService | None = None,
        store: RuntimeStateStore | None = None,
        context_compaction: ContextCompactionService | None = None,
        telemetry_service: TelemetryService | None = None,
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle
        self._data_store = data_store
        self._event_bus = event_bus
        self._context_store = context_store
        self._skill_runtime = skill_runtime
        self._store = store
        self._history: list[WorkflowExecutionResult] = []
        self._context_compaction = context_compaction
        self._telemetry_service = telemetry_service

    def execute_primary_workflow(self, app_instance_id: str, trigger: str = "manual", inputs: dict[str, Any] | None = None) -> WorkflowExecutionResult:
        return self.execute_workflow(app_instance_id=app_instance_id, workflow_id=None, trigger=trigger, inputs=inputs)

    def execute_workflow(
        self,
        app_instance_id: str,
        workflow_id: str | None = None,
        trigger: str = "manual",
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowExecutionResult:
        instance = self._lifecycle.get_instance(app_instance_id)
        blueprint = self._registry.get_blueprint(instance.blueprint_id)
        if not blueprint.workflows:
            raise WorkflowExecutorError(f"No workflow defined for blueprint: {blueprint.id}")

        workflow = blueprint.workflows[0] if workflow_id is None else next(
            (item for item in blueprint.workflows if item.id == workflow_id),
            None,
        )
        if workflow is None:
            raise WorkflowExecutorError(f"Workflow not found: {workflow_id}")

        steps: list[WorkflowStepExecution] = []
        payload = inputs or {}
        execution_context: dict[str, Any] = {"inputs": payload, "steps": {}}

        previous_stage = None
        if self._context_store is not None:
            previous_stage = self._context_store.ensure_context(app_instance_id).current_stage
            self._context_store.update_context(
                app_instance_id,
                current_stage=f"workflow:{workflow.id}",
                status="active",
            )
            self._context_store.append_entry(
                app_instance_id,
                section="open_loops",
                key="workflow-trigger",
                value={"workflow_id": workflow.id, "trigger": trigger, "inputs": payload},
                tags=["workflow", "trigger"],
            )

        for step in workflow.steps:
            if not self._should_run_step(step.config, execution_context):
                skipped = WorkflowStepExecution(
                    step_id=step.id,
                    ref=step.ref,
                    kind=step.kind,
                    status="skipped",
                    detail={"reason": "condition not met"},
                    output={},
                )
                steps.append(skipped)
                execution_context["steps"][step.id] = skipped.output
                continue

            executed = self._execute_step(
                app_instance_id,
                workflow.id,
                step.kind,
                step.id,
                step.ref,
                step.config,
                payload,
                execution_context,
            )
            steps.append(executed)
            execution_context["steps"][step.id] = executed.output

        if self._context_store is not None:
            self._context_store.append_entry(
                app_instance_id,
                section="artifacts",
                key=f"workflow-result:{workflow.id}",
                value={"step_count": len(steps), "trigger": trigger},
                tags=["workflow", "result"],
            )

        execution_status = "completed" if all(step.status == "completed" for step in steps) else "partial"
        result_record = self._data_store.put_record(
            namespace_id=f"{app_instance_id}:runtime_state",
            key=f"workflow_execution:{workflow.id}",
            value={
                "workflow_id": workflow.id,
                "trigger": trigger,
                "status": execution_status,
                "steps": [step.model_dump(mode="json") for step in steps],
            },
            tags=["workflow", "execution", workflow.id],
        )

        if self._context_store is not None:
            self._context_store.append_entry(
                app_instance_id,
                section="artifacts",
                key=f"runtime-state:{workflow.id}",
                value={"record_id": result_record.record_id, "status": execution_status},
                tags=["workflow", "runtime-state"],
            )

        workflow_outputs = self._build_workflow_outputs(execution_context, steps)
        completed_at = datetime.now(UTC)
        result = WorkflowExecutionResult(
            app_instance_id=app_instance_id,
            blueprint_id=blueprint.id,
            workflow_id=workflow.id,
            trigger=trigger,
            status=execution_status,
            outputs=workflow_outputs,
            steps=steps,
            completed_at=completed_at,
            failed_step_ids=[step.step_id for step in steps if step.status == "failed"],
        )
        self._history.append(result)
        self._persist_history()
        if self._telemetry_service is not None:
            interaction_id = f"workflow:{app_instance_id}:{workflow.id}:{int(completed_at.timestamp())}"
            self._telemetry_service.record_step(
                StepTelemetryRecord(
                    interaction_id=interaction_id,
                    step_id=workflow.id,
                    step_type="system",
                    name="workflow_executor",
                    success=result.status == "completed",
                    error_code="workflow_partial" if result.status != "completed" else None,
                    payload_summary={
                        "failed_step_ids": result.failed_step_ids,
                        "completed_steps": result.outputs.get("completed_steps", []),
                    },
                ),
                app_id=instance.blueprint_id,
            )
            self._telemetry_service.bind_versions(
                VersionBindingRecord(
                    interaction_id=interaction_id,
                    app_version=instance.release_version,
                ),
                app_id=instance.blueprint_id,
            )
        if self._context_compaction is not None:
            if previous_stage is not None and previous_stage != f"workflow:{workflow.id}" and self._context_compaction.should_compact(app_instance_id, "stage_change"):
                self._context_compaction.compact(app_instance_id, reason="stage_change")
            event_name = "workflow_failure" if result.status == "partial" and any(step.status == "failed" for step in result.steps) else "workflow_complete"
            if self._context_compaction.should_compact(app_instance_id, event_name):
                self._context_compaction.compact(app_instance_id, reason=event_name)
        return result

    def _execute_step(
        self,
        app_instance_id: str,
        workflow_id: str,
        kind: str,
        step_id: str,
        ref: str,
        config: dict[str, Any],
        inputs: dict[str, Any],
        execution_context: dict[str, Any],
    ) -> WorkflowStepExecution:
        if kind == "module" and ref == "state.set":
            key = str(config.get("key", f"workflow.{workflow_id}.{step_id}"))
            value = self._resolve_value(config.get("value", inputs), execution_context)
            record = self._data_store.put_record(
                namespace_id=f"{app_instance_id}:app_data",
                key=key,
                value=value if isinstance(value, dict) else {"value": value},
                tags=["workflow", workflow_id, step_id],
            )
            return WorkflowStepExecution(
                step_id=step_id,
                ref=ref,
                kind=kind,
                status="completed",
                detail={"record_id": record.record_id, "key": key},
                output={"record_id": record.record_id, "key": key, "value": record.value},
            )

        if kind == "module" and ref == "state.get":
            key = str(config.get("key", ""))
            if not key:
                return WorkflowStepExecution(
                    step_id=step_id,
                    ref=ref,
                    kind=kind,
                    status="skipped",
                    detail={"reason": "missing key"},
                    output={},
                )
            records = self._data_store.list_records(f"{app_instance_id}:app_data")
            record = next((item for item in records if item.key == key), None)
            if self._context_store is not None:
                self._context_store.append_entry(
                    app_instance_id,
                    section="artifacts",
                    key=f"state-read:{key}",
                    value={} if record is None else record.value,
                    tags=["workflow", "state-get"],
                )
            return WorkflowStepExecution(
                step_id=step_id,
                ref=ref,
                kind=kind,
                status="completed" if record is not None else "skipped",
                detail={"key": key, "found": record is not None},
                output={} if record is None else {"key": key, "value": record.value},
            )

        if kind == "event":
            event_name = str(config.get("event_name", ref))
            event_payload = self._resolve_value(config.get("payload", inputs), execution_context)
            result = self._event_bus.publish(
                event_name=event_name,
                source="workflow",
                app_instance_id=app_instance_id,
                payload={"workflow_id": workflow_id, "step_id": step_id, **(event_payload if isinstance(event_payload, dict) else {"value": event_payload})},
            )
            return WorkflowStepExecution(
                step_id=step_id,
                ref=ref,
                kind=kind,
                status="completed",
                detail={"event_id": result.event.event_id, "event_name": event_name},
                output={"event_id": result.event.event_id, "event_name": event_name},
            )

        if kind == "human_task":
            if self._context_store is not None:
                self._context_store.append_entry(
                    app_instance_id,
                    section="questions",
                    key=f"human-task:{step_id}",
                    value={"ref": ref, "config": config},
                    tags=["workflow", "human-task"],
                )
            return WorkflowStepExecution(
                step_id=step_id,
                ref=ref,
                kind=kind,
                status="skipped",
                detail={"reason": "human task placeholder", "ref": ref},
                output={"placeholder": "human_task", "ref": ref},
            )

        if kind == "skill":
            if ref not in self._registry.get_blueprint(self._lifecycle.get_instance(app_instance_id).blueprint_id).required_skills:
                if self._context_store is not None:
                    self._context_store.append_entry(
                        app_instance_id,
                        section="constraints",
                        key=f"skill-policy:{step_id}",
                        value={"ref": ref, "status": "blocked", "reason": "skill not declared in blueprint"},
                        tags=["workflow", "skill-policy"],
                    )
                return WorkflowStepExecution(
                    step_id=step_id,
                    ref=ref,
                    kind=kind,
                    status="failed",
                    detail={"reason": "skill not declared in blueprint", "ref": ref},
                    output={},
                )
            if self._skill_runtime is None:
                if self._context_store is not None:
                    self._context_store.append_entry(
                        app_instance_id,
                        section="open_loops",
                        key=f"skill-step:{step_id}",
                        value={"ref": ref, "config": config},
                        tags=["workflow", "skill-step"],
                    )
                return WorkflowStepExecution(
                    step_id=step_id,
                    ref=ref,
                    kind=kind,
                    status="skipped",
                    detail={"reason": "skill execution placeholder", "ref": ref},
                    output={"placeholder": "skill", "ref": ref},
                )
            try:
                mapped_inputs = self._resolve_value(config.get("inputs", inputs), execution_context)
                mapped_config = self._resolve_value(config, execution_context)
                working_set = None
                if self._context_compaction is not None:
                    working_set = self._context_compaction.build_working_set(app_instance_id).model_dump(mode="json")
                request = SkillExecutionRequest(
                    skill_id=ref,
                    app_instance_id=app_instance_id,
                    workflow_id=workflow_id,
                    step_id=step_id,
                    inputs=(mapped_inputs if isinstance(mapped_inputs, dict) else {"value": mapped_inputs}) | ({"working_set": working_set} if working_set is not None else {}),
                    config=mapped_config if isinstance(mapped_config, dict) else {"value": mapped_config},
                )
                result = self._skill_runtime.execute(request)
                if self._context_store is not None:
                    target_section = "artifacts" if result.status == "completed" else "open_loops"
                    self._context_store.append_entry(
                        app_instance_id,
                        section=target_section,
                        key=f"skill-result:{step_id}",
                        value={"output": result.output, "error": result.error, "status": result.status},
                        tags=["workflow", "skill-step", ref],
                    )
                return WorkflowStepExecution(
                    step_id=step_id,
                    ref=ref,
                    kind=kind,
                    status="completed" if result.status == "completed" else "failed",
                    detail={
                        "skill_id": ref,
                        "status": result.status,
                        "error": result.error,
                        "error_detail": result.error_detail,
                    },
                    output=result.output,
                )
            except SkillRuntimeError:
                if self._context_store is not None:
                    self._context_store.append_entry(
                        app_instance_id,
                        section="open_loops",
                        key=f"skill-step:{step_id}",
                        value={"ref": ref, "config": config, "status": "unhandled"},
                        tags=["workflow", "skill-step"],
                    )
                return WorkflowStepExecution(
                    step_id=step_id,
                    ref=ref,
                    kind=kind,
                    status="skipped",
                    detail={"reason": "skill handler missing", "ref": ref},
                    output={"placeholder": "skill", "ref": ref},
                )

        return WorkflowStepExecution(
            step_id=step_id,
            ref=ref,
            kind=kind,
            status="skipped",
            detail={"reason": "unsupported step"},
            output={},
        )

    def _should_run_step(self, config: dict[str, Any], execution_context: dict[str, Any]) -> bool:
        when = config.get("when")
        if not isinstance(when, dict):
            return True
        actual = self._resolve_value(when.get("source"), execution_context)
        expected = when.get("equals")
        return actual == expected

    def _build_workflow_outputs(
        self,
        execution_context: dict[str, Any],
        steps: list[WorkflowStepExecution],
    ) -> dict[str, Any]:
        completed_steps = [step.step_id for step in steps if step.status == "completed"]
        skipped_steps = [step.step_id for step in steps if step.status == "skipped"]
        return {
            "inputs": execution_context.get("inputs", {}),
            "completed_steps": completed_steps,
            "skipped_steps": skipped_steps,
            "step_outputs": execution_context.get("steps", {}),
        }

    def list_history(self, app_instance_id: str | None = None) -> list[WorkflowExecutionResult]:
        if app_instance_id is None:
            return list(self._history)
        return [item for item in self._history if item.app_instance_id == app_instance_id]

    def list_recent_failures(self, app_instance_id: str | None = None) -> list[WorkflowExecutionResult]:
        history = self.list_history(app_instance_id)
        return [item for item in history if item.status == "partial" and any(step.status == "failed" for step in item.steps)]

    def retry_last_failure(self, app_instance_id: str) -> WorkflowExecutionResult:
        history = self.list_history(app_instance_id)
        retry_candidates = [item for item in history if item.status == "partial"]
        if not retry_candidates:
            raise WorkflowExecutorError(f"No failed workflow execution found for app instance: {app_instance_id}")
        last = retry_candidates[-1]
        retry_inputs = deepcopy(last.outputs.get("inputs", {})) if isinstance(last.outputs, dict) else {}
        retried = self.execute_workflow(
            app_instance_id=app_instance_id,
            workflow_id=last.workflow_id,
            trigger=f"retry:{last.trigger}",
            inputs=retry_inputs if isinstance(retry_inputs, dict) else {},
        )
        previous_failed = set(last.failed_step_ids)
        retried_failed = set(retried.failed_step_ids)
        retried.retry_of_completed_at = last.completed_at
        retried.retry_comparison = WorkflowRetryComparison(
            previous_status=last.status,
            retried_status=retried.status,
            previous_failed_step_ids=list(last.failed_step_ids),
            retried_failed_step_ids=list(retried.failed_step_ids),
            resolved_failed_step_ids=sorted(previous_failed - retried_failed),
            newly_failed_step_ids=sorted(retried_failed - previous_failed),
            unchanged_failed_step_ids=sorted(previous_failed & retried_failed),
        )
        if self._history:
            self._history[-1] = retried
            self._persist_history()
        return retried

    def _persist_history(self) -> None:
        if self._store is None:
            return
        self._store.save_collection("workflow_execution_history", self._history)

    def _resolve_value(self, value: Any, execution_context: dict[str, Any]) -> Any:
        if isinstance(value, dict) and "$literal" in value:
            return self._apply_transform(value.get("$literal"), value.get("transform"))
        if isinstance(value, dict) and "$from_step" in value:
            step_id = str(value["$from_step"])
            field = value.get("field")
            step_output = execution_context.get("steps", {}).get(step_id, {})
            resolved = step_output if field is None else (step_output.get(str(field)) if isinstance(step_output, dict) else None)
            if resolved is None and "default" in value:
                resolved = value.get("default")
            return self._apply_transform(resolved, value.get("transform"))
        if isinstance(value, dict) and "$from_inputs" in value:
            input_key = str(value["$from_inputs"])
            resolved = execution_context.get("inputs", {}).get(input_key)
            if resolved is None and "default" in value:
                resolved = value.get("default")
            return self._apply_transform(resolved, value.get("transform"))
        if isinstance(value, dict):
            return {key: self._resolve_value(item, execution_context) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(item, execution_context) for item in value]
        return value

    def _apply_transform(self, value: Any, transform: Any) -> Any:
        if not transform or value is None:
            return value
        if transform == "lowercase":
            return str(value).lower()
        if transform == "uppercase":
            return str(value).upper()
        if transform == "stringify":
            return str(value)
        if transform == "wrap_object":
            return {"value": value}
        return value
