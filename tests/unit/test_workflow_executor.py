from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.workflow_executor import WorkflowExecutorService


client = TestClient(app)


def test_workflow_executor_runs_state_and_event_steps(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-executor-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-executor-ns"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.exec",
            name="Workflow Exec App",
            goal="execute deterministic workflow",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.exec",
                    "name": "exec",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "step.set", "kind": "module", "ref": "state.set", "config": {"key": "draft", "value": {"status": "ok"}}},
                        {"id": "step.get", "kind": "module", "ref": "state.get", "config": {"key": "draft"}},
                        {"id": "step.event", "kind": "event", "ref": "workflow.completed", "config": {"event_name": "workflow.completed"}},
                    ],
                }
            ],
            required_modules=["state.get", "state.set"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.exec", user_id="workflow-user")

    result = executor.execute_primary_workflow(install_result.app_instance_id, inputs={"source": "test"})

    assert result.workflow_id == "wf.exec"
    assert len(result.steps) == 3
    records = data_store.list_records(f"{install_result.app_instance_id}:app_data")
    assert any(item.key == "draft" for item in records)
    events = event_bus.list_events("workflow.completed")
    assert len(events) == 1
    context = context_store.get_context(install_result.app_instance_id)
    assert any(item.key.startswith("workflow-result:") for item in context.entries)


def test_workflow_executor_supports_workflow_selection_and_placeholders(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-selection-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-selection-ns"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.select",
            name="Workflow Select App",
            goal="run selected workflow",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.primary",
                    "name": "primary",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.primary", "kind": "module", "ref": "state.set", "config": {"key": "primary", "value": {"ok": True}}},
                    ],
                },
                {
                    "id": "wf.secondary",
                    "name": "secondary",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "ask.human", "kind": "human_task", "ref": "human.review", "config": {"prompt": "please review"}},
                        {"id": "call.skill", "kind": "skill", "ref": "skill.review", "config": {"mode": "draft"}},
                    ],
                },
            ],
            required_modules=["state.set"],
            required_skills=["skill.review"],
        )
    )
    install_result = installer.install_app("bp.workflow.select", user_id="workflow-select-user")

    result = executor.execute_workflow(
        install_result.app_instance_id,
        workflow_id="wf.secondary",
        inputs={"topic": "selection"},
    )

    assert result.workflow_id == "wf.secondary"
    assert result.status == "partial"
    assert len(result.steps) == 2
    assert all(step.status == "skipped" for step in result.steps)
    runtime_records = data_store.list_records(f"{install_result.app_instance_id}:runtime_state")
    assert any(item.key == "workflow_execution:wf.secondary" for item in runtime_records)
    context = context_store.get_context(install_result.app_instance_id)
    assert any(item.key == "human-task:ask.human" for item in context.entries)
    assert any(item.key == "skill-step:call.skill" for item in context.entries)


def test_workflow_executor_passes_step_outputs_between_steps(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-step-outputs-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-step-outputs-ns"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.outputs",
            name="Workflow Outputs App",
            goal="pass outputs between steps",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.outputs",
                    "name": "outputs",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "step.seed", "kind": "module", "ref": "state.set", "config": {"key": "seed", "value": {"message": "hello"}}},
                        {"id": "step.read", "kind": "module", "ref": "state.get", "config": {"key": "seed"}},
                        {"id": "step.copy", "kind": "module", "ref": "state.set", "config": {"key": "copied", "value": {"$from_step": "step.read", "field": "value"}}},
                        {"id": "step.emit", "kind": "event", "ref": "workflow.outputs.done", "config": {"event_name": "workflow.outputs.done", "payload": {"$from_step": "step.copy", "field": "value"}}},
                    ],
                }
            ],
            required_modules=["state.get", "state.set"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.outputs", user_id="workflow-output-user")

    result = executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.outputs")

    assert result.status == "completed"
    records = data_store.list_records(f"{install_result.app_instance_id}:app_data")
    copied = next(item for item in records if item.key == "copied")
    assert copied.value["message"] == "hello"
    event = event_bus.list_events("workflow.outputs.done")[0]
    assert event.payload["message"] == "hello"
    assert result.steps[-1].output["event_name"] == "workflow.outputs.done"


def test_workflow_executor_supports_conditional_steps_and_outputs_summary(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-conditions-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-conditions-ns"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.conditions",
            name="Workflow Condition App",
            goal="support conditional execution",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.conditional",
                    "name": "conditional",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.flag", "kind": "module", "ref": "state.set", "config": {"key": "flag", "value": {"enabled": True}}},
                        {"id": "copy.enabled", "kind": "module", "ref": "state.set", "config": {"key": "copy-enabled", "value": {"$from_inputs": "payload"}, "when": {"source": {"$from_inputs": "run_copy"}, "equals": True}}},
                        {"id": "copy.disabled", "kind": "module", "ref": "state.set", "config": {"key": "copy-disabled", "value": {"$from_inputs": "payload"}, "when": {"source": {"$from_inputs": "run_copy"}, "equals": False}}},
                    ],
                }
            ],
            required_modules=["state.set"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.conditions", user_id="workflow-conditions-user")

    result = executor.execute_workflow(
        install_result.app_instance_id,
        workflow_id="wf.conditional",
        inputs={"run_copy": True, "payload": {"name": "demo"}},
    )

    assert result.status == "partial"
    assert "copy.enabled" in result.outputs["completed_steps"]
    assert "copy.disabled" in result.outputs["skipped_steps"]
    assert "copy.enabled" in result.outputs["step_outputs"]
    records = data_store.list_records(f"{install_result.app_instance_id}:app_data")
    assert any(item.key == "copy-enabled" for item in records)
    assert all(item.key != "copy-disabled" for item in records)


def test_workflow_execution_api_flow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.api",
            "name": "Workflow API App",
            "goal": "run workflow via api",
            "roles": [],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.api.exec",
                    "name": "api exec",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.settings", "kind": "module", "ref": "state.set", "config": {"key": "settings", "value": {"theme": "dark"}}},
                        {"id": "emit.done", "kind": "event", "ref": "workflow.api.done", "config": {"event_name": "workflow.api.done"}},
                    ],
                }
            ],
            "views": [],
            "required_modules": ["state.set"],
            "required_skills": [],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive"
            }
        },
    )
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.workflow.api/install",
        json={"user_id": "workflow-api-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"trigger": "api", "inputs": {"request_id": "r1"}},
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["workflow_id"] == "wf.api.exec"
    assert len(execute_response.json()["steps"]) == 2

    records_response = client.get(f"/data/namespaces/{app_instance_id}:app_data/records")
    assert records_response.status_code == 200
    assert any(item["key"] == "settings" for item in records_response.json())

    events_response = client.get("/events", params={"event_name": "workflow.api.done"})
    assert events_response.status_code == 200
    assert any(item["app_instance_id"] == app_instance_id for item in events_response.json())
