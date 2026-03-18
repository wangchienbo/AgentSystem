from app.models.app_blueprint import AppBlueprint
from app.models.app_config import AppConfigRequest
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.app_config_service import AppConfigService
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


def test_system_app_config_skill_executes_through_skill_runtime() -> None:
    store = RuntimeStateStore(base_dir="data/test-system-app-config-skill")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir="data/test-system-app-config-skill-ns", store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    app_config = AppConfigService(data_store=data_store, store=store)
    skill_runtime = SkillRuntimeService(store=store)

    def app_config_handler(request: SkillExecutionRequest) -> SkillExecutionResult:
        result = app_config.execute(request.app_instance_id, AppConfigRequest(**request.inputs))
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    skill_runtime.register_handler("system.app_config", app_config_handler)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
        app_config_service=app_config,
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
            id="bp.system.app.config",
            name="System App Config",
            goal="exercise config skill",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.system.app.config",
                    "name": "system config",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set", "kind": "skill", "ref": "system.app_config", "config": {"inputs": {"operation": "set", "key": "ui", "value": {"theme": "dark"}}}},
                        {"id": "get", "kind": "skill", "ref": "system.app_config", "config": {"inputs": {"operation": "get", "key": "ui"}}},
                    ],
                }
            ],
            required_modules=[],
            required_skills=["system.app_config"],
        )
    )
    install_result = installer.install_app("bp.system.app.config", user_id="system-config-user")

    result = executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.system.app.config")

    assert result.status == "completed"
    assert result.steps[1].output["value"]["theme"] == "dark"
    snapshot = app_config.get_snapshot(install_result.app_instance_id)
    assert snapshot.values["ui"]["theme"] == "dark"
