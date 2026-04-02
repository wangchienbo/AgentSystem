from pathlib import Path

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


def _build_services(tmp_path: Path):
    store = RuntimeStateStore(base_dir=str(tmp_path / "phase4-primitives-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "phase4-primitives-ns"), store=store)
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
    return registry, installer, executor, data_store, context_store


def test_workflow_executor_supports_data_primitives(tmp_path: Path) -> None:
    registry, installer, executor, data_store, context_store = _build_services(tmp_path)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.phase4.data",
            name="Workflow Phase4 Data App",
            goal="exercise data primitives",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.phase4.data",
                    "name": "phase4 data",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "write.alpha", "kind": "module", "ref": "data.write", "config": {"key": "alpha", "value": {"name": "A"}}},
                        {"id": "write.beta", "kind": "module", "ref": "data.write", "config": {"key": "beta", "value": {"name": "B"}}},
                        {"id": "read.alpha", "kind": "module", "ref": "data.read", "config": {"key": "alpha"}},
                        {"id": "list.all", "kind": "module", "ref": "data.list", "config": {}},
                    ],
                }
            ],
            required_modules=["data.write", "data.read", "data.list"],
            required_skills=[],
        )
    )
    install = installer.install_app("bp.workflow.phase4.data", user_id="phase4-data-user")

    result = executor.execute_workflow(install.app_instance_id, workflow_id="wf.phase4.data")

    assert result.status == "completed"
    assert result.outputs["step_outputs"]["read.alpha"]["value"]["name"] == "A"
    assert result.outputs["step_outputs"]["list.all"]["count"] == 2
    records = data_store.list_records(f"{install.app_instance_id}:app_data")
    assert {item.key for item in records} >= {"alpha", "beta"}
    context = context_store.get_context(install.app_instance_id)
    assert any(item.key == "data-write:alpha" for item in context.entries)
    assert any(item.key == "data-list:list.all" for item in context.entries)


def test_workflow_executor_supports_context_primitives(tmp_path: Path) -> None:
    registry, installer, executor, _data_store, context_store = _build_services(tmp_path)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.phase4.context",
            name="Workflow Phase4 Context App",
            goal="exercise context primitives",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.phase4.context",
                    "name": "phase4 context",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "goal.set", "kind": "module", "ref": "context.set_goal", "config": {"goal": "finish phase 4"}},
                        {"id": "stage.set", "kind": "module", "ref": "context.set_stage", "config": {"stage": "phase4:active"}},
                        {"id": "note.append", "kind": "module", "ref": "context.append", "config": {"section": "decisions", "key": "phase4-note", "value": {"status": "in-progress"}, "tags": ["phase4", "workflow"]}},
                    ],
                }
            ],
            required_modules=["context.set_goal", "context.set_stage", "context.append"],
            required_skills=[],
        )
    )
    install = installer.install_app("bp.workflow.phase4.context", user_id="phase4-context-user")

    result = executor.execute_workflow(install.app_instance_id, workflow_id="wf.phase4.context")

    assert result.status == "completed"
    context = context_store.get_context(install.app_instance_id)
    assert context.current_goal == "finish phase 4"
    assert context.current_stage == "phase4:active"
    note = next(item for item in context.entries if item.key == "phase4-note")
    assert note.section == "decisions"
    assert note.value["status"] == "in-progress"
    assert note.tags == ["phase4", "workflow"]
