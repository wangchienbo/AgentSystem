from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.skill_runtime import SkillRuntimeService
from app.services.workflow_executor import WorkflowExecutorService


client = TestClient(app)


def test_skill_runtime_executes_registered_handler_inside_workflow() -> None:
    store = RuntimeStateStore(base_dir="data/test-skill-runtime")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir="data/test-skill-runtime-ns", store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    skill_runtime = SkillRuntimeService(store=store)

    def echo_handler(request: SkillExecutionRequest) -> SkillExecutionResult:
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output={"message": request.config.get("message", "hi")})

    skill_runtime.register_handler("skill.echo", echo_handler)
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
        skill_runtime=skill_runtime,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.skill.runtime",
            name="Skill Runtime App",
            goal="execute skill steps",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.skill.runtime",
                    "name": "skill runtime",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "step.skill", "kind": "skill", "ref": "skill.echo", "config": {"message": "hello from skill"}},
                    ],
                }
            ],
            required_modules=[],
            required_skills=["skill.echo"],
        )
    )
    install_result = installer.install_app("bp.skill.runtime", user_id="skill-runtime-user")

    result = executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.skill.runtime")

    assert result.status == "completed"
    assert result.steps[0].output["message"] == "hello from skill"
    context = context_store.get_context(install_result.app_instance_id)
    assert any(item.key == "skill-result:step.skill" for item in context.entries)
    assert len(skill_runtime.list_executions()) == 1


def test_skill_runtime_supports_input_mapping_and_failure_capture() -> None:
    store = RuntimeStateStore(base_dir="data/test-skill-runtime-mapping")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir="data/test-skill-runtime-mapping-ns", store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    skill_runtime = SkillRuntimeService(store=store)

    def mapping_handler(request: SkillExecutionRequest) -> SkillExecutionResult:
        payload = request.inputs.get("payload", {})
        if payload.get("mode") == "fail":
            raise RuntimeError("forced failure")
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output={"seen": payload})

    skill_runtime.register_handler("skill.map", mapping_handler)
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
        skill_runtime=skill_runtime,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.skill.mapping",
            name="Skill Mapping App",
            goal="map inputs into skill calls",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.skill.mapping",
                    "name": "skill mapping",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "seed", "kind": "module", "ref": "state.set", "config": {"key": "seed", "value": {"mode": "ok", "text": "mapped"}}},
                        {"id": "call.skill", "kind": "skill", "ref": "skill.map", "config": {"inputs": {"payload": {"$from_step": "seed", "field": "value"}}}},
                        {"id": "call.fail", "kind": "skill", "ref": "skill.map", "config": {"inputs": {"payload": {"mode": "fail"}}}},
                    ],
                }
            ],
            required_modules=["state.set"],
            required_skills=["skill.map"],
        )
    )
    install_result = installer.install_app("bp.skill.mapping", user_id="skill-mapping-user")

    result = executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.skill.mapping")

    assert result.status == "partial"
    assert result.steps[1].status == "completed"
    assert result.steps[1].output["seen"]["text"] == "mapped"
    assert result.steps[2].status == "failed"
    assert "forced failure" in result.steps[2].detail["error"]
    context = context_store.get_context(install_result.app_instance_id)
    assert any(item.section == "open_loops" and item.key == "skill-result:call.fail" for item in context.entries)


def test_skill_runtime_api_flow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.skill.runtime.api",
            "name": "Skill Runtime API App",
            "goal": "run a real skill step",
            "roles": [],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.skill.api",
                    "name": "skill api",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "step.echo", "kind": "skill", "ref": "skill.echo", "config": {"payload": {"text": "api-skill"}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": [],
            "required_skills": ["skill.echo"],
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
        "/registry/apps/bp.skill.runtime.api/install",
        json={"user_id": "skill-runtime-api-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.skill.api", "trigger": "api", "inputs": {"from": "api"}},
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["steps"][0]["output"]["echo"]["text"] == "api-skill"

    executions_response = client.get("/skill-runtime/executions")
    assert executions_response.status_code == 200
    assert len(executions_response.json()) >= 1
