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


def test_workflow_execution_records_failed_step_ids_for_policy_block() -> None:
    tmp_path = Path("/tmp")
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-failure-observability-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-failure-observability-ns"), store=store)
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
            id="bp.workflow.failure-observability",
            name="Workflow Failure Observability App",
            goal="surface failed workflow step ids",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.failure.observe",
                    "name": "observe failure",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "test"}},
                    ],
                }
            ],
            required_modules=[],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.failure-observability", user_id="workflow-failure-user")

    result = executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.failure.observe")

    assert result.status == "partial"
    assert result.failed_step_ids == ["blocked.skill"]
    assert result.steps[0].status == "failed"
    assert result.steps[0].detail["reason"] == "skill not declared in blueprint"
