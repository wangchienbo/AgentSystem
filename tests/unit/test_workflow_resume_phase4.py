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


def _build_services(tmp_path: Path):
    store = RuntimeStateStore(base_dir=str(tmp_path / "phase4-resume-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "phase4-resume-ns"), store=store)
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


def test_resume_last_interrupted_supports_paused_and_waiting_workflows(tmp_path: Path) -> None:
    registry, installer, executor, _context_store = _build_services(tmp_path)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.phase4.resume.local",
            name="Workflow Phase4 Resume Local App",
            goal="resume interrupted workflows",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.phase4.resume.pause",
                    "name": "resume pause",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "pause", "kind": "module", "ref": "workflow.pause_for_human", "config": {"message": "need approval"}},
                        {"id": "finish", "kind": "module", "ref": "workflow.complete", "config": {"result": {"ok": True}, "when": {"source": {"$from_inputs": "approved", "default": False}, "equals": True}}},
                    ],
                }
            ],
            required_modules=["workflow.pause_for_human", "workflow.complete"],
            required_skills=[],
        )
    )
    install = installer.install_app("bp.workflow.phase4.resume.local", user_id="phase4-resume-local-user")

    paused = executor.execute_workflow(install.app_instance_id, workflow_id="wf.phase4.resume.pause", inputs={"approved": False})
    assert paused.status == "paused_for_human"

    resumed = executor.resume_last_interrupted(install.app_instance_id, resume_inputs={"approved": True})
    assert resumed.trigger.startswith("resume:")
    assert resumed.retry_comparison is not None
    assert resumed.retry_comparison.previous_status == "paused_for_human"


def test_resume_last_interrupted_api_flow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.phase4.resume.api",
            "name": "Workflow Phase4 Resume API App",
            "goal": "resume interrupted workflows through api",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.phase4.resume.api",
                    "name": "resume api",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "wait", "kind": "module", "ref": "workflow.wait_for_event", "config": {"event_name": "signal.go"}},
                        {"id": "complete", "kind": "module", "ref": "workflow.complete", "config": {"result": {"done": True}, "when": {"source": {"$from_inputs": "event_received", "default": False}, "equals": True}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": ["workflow.wait_for_event", "workflow.complete"],
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
        "/registry/apps/bp.workflow.phase4.resume.api/install",
        json={"user_id": "phase4-resume-api-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.phase4.resume.api", "trigger": "api", "inputs": {"event_received": False}},
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["status"] == "waiting_for_event"

    resume_response = client.post(
        f"/apps/{app_instance_id}/workflows/resume-last-interrupted",
        json={"resume_inputs": {"event_received": True}},
    )
    assert resume_response.status_code == 200
    resumed = resume_response.json()
    assert resumed["trigger"].startswith("resume:")
    assert resumed["retry_comparison"]["previous_status"] == "waiting_for_event"
