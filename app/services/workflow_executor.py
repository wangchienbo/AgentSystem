from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.workflow_execution import WorkflowExecutionResult, WorkflowStepExecution
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.lifecycle import AppLifecycleService


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
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle
        self._data_store = data_store
        self._event_bus = event_bus
        self._context_store = context_store

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

        if self._context_store is not None:
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
        return WorkflowExecutionResult(
            app_instance_id=app_instance_id,
            blueprint_id=blueprint.id,
            workflow_id=workflow.id,
            trigger=trigger,
            status=execution_status,
            outputs=workflow_outputs,
            steps=steps,
            completed_at=completed_at,
        )

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
            "completed_steps": completed_steps,
            "skipped_steps": skipped_steps,
            "step_outputs": execution_context.get("steps", {}),
        }

    def _resolve_value(self, value: Any, execution_context: dict[str, Any]) -> Any:
        if isinstance(value, dict) and "$from_step" in value:
            step_id = str(value["$from_step"])
            field = value.get("field")
            step_output = execution_context.get("steps", {}).get(step_id, {})
            if field is None:
                return step_output
            if isinstance(step_output, dict):
                return step_output.get(str(field))
            return None
        if isinstance(value, dict) and "$from_inputs" in value:
            input_key = str(value["$from_inputs"])
            return execution_context.get("inputs", {}).get(input_key)
        return value
