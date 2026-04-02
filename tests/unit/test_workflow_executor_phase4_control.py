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
    store = RuntimeStateStore(base_dir=str(tmp_path / "phase4-control-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "phase4-control-ns"), store=store)
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
    return registry, installer, executor, context_store


def test_workflow_executor_supports_wait_for_event_and_pause_for_human(tmp_path: Path) -> None:
    registry, installer, executor, context_store = _build_services(tmp_path)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.phase4.wait",
            name="Workflow Phase4 Wait App",
            goal="exercise wait and pause controls",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.phase4.wait",
                    "name": "phase4 wait",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "wait.event", "kind": "module", "ref": "workflow.wait_for_event", "config": {"event_name": "approval.received", "resume_hint": "resume when approval event arrives"}},
                    ],
                },
                {
                    "id": "wf.phase4.pause",
                    "name": "phase4 pause",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "pause.human", "kind": "module", "ref": "workflow.pause_for_human", "config": {"message": "need reviewer approval", "required_action": "approve request"}},
                    ],
                },
            ],
            required_modules=["workflow.wait_for_event", "workflow.pause_for_human"],
            required_skills=[],
        )
    )
    install = installer.install_app("bp.workflow.phase4.wait", user_id="phase4-wait-user")

    waiting = executor.execute_workflow(install.app_instance_id, workflow_id="wf.phase4.wait")
    paused = executor.execute_workflow(install.app_instance_id, workflow_id="wf.phase4.pause")

    assert waiting.status == "waiting_for_event"
    assert waiting.waiting_step_ids == ["wait.event"]
    assert waiting.unresolved_step_ids == ["wait.event"]
    assert waiting.steps[0].detail["event_name"] == "approval.received"

    assert paused.status == "paused_for_human"
    assert paused.pause_step_ids == ["pause.human"]
    assert paused.unresolved_step_ids == ["pause.human"]
    assert paused.steps[0].output["required_action"] == "approve request"

    context = context_store.get_context(install.app_instance_id)
    assert any(item.key == "wait-for-event:wait.event" for item in context.entries)
    assert any(item.key == "pause-for-human:pause.human" for item in context.entries)


def test_workflow_executor_supports_fail_and_complete_control_steps(tmp_path: Path) -> None:
    registry, installer, executor, _context_store = _build_services(tmp_path)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.phase4.control",
            name="Workflow Phase4 Control App",
            goal="exercise fail and complete controls",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.phase4.fail",
                    "name": "phase4 fail",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "force.fail", "kind": "module", "ref": "workflow.fail", "config": {"reason": "explicit failure requested"}},
                    ],
                },
                {
                    "id": "wf.phase4.complete",
                    "name": "phase4 complete",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "force.complete", "kind": "module", "ref": "workflow.complete", "config": {"result": {"status": "done"}}},
                    ],
                },
            ],
            required_modules=["workflow.fail", "workflow.complete"],
            required_skills=[],
        )
    )
    install = installer.install_app("bp.workflow.phase4.control", user_id="phase4-control-user")

    failed = executor.execute_workflow(install.app_instance_id, workflow_id="wf.phase4.fail")
    completed = executor.execute_workflow(install.app_instance_id, workflow_id="wf.phase4.complete")

    assert failed.status == "partial"
    assert failed.failed_step_ids == ["force.fail"]
    assert failed.unresolved_step_ids == ["force.fail"]
    assert failed.steps[0].detail["forced_failure"] is True

    assert completed.status == "completed"
    assert completed.steps[0].output["forced_completion"] is True
    assert completed.steps[0].output["result"]["status"] == "done"
