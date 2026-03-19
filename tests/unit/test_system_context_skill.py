from pathlib import Path

from app.models.app_blueprint import AppBlueprint
from app.models.context_skill import ContextSkillRequest
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.services.app_config_service import AppConfigService
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.context_skill_service import ContextSkillService
from app.services.event_bus import EventBusService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.skill_runtime import SkillRuntimeService
from app.services.workflow_executor import WorkflowExecutorService


def test_system_context_skill_executes_through_runtime(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "namespaces"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    context_skill = ContextSkillService(context_store=context_store)
    app_config = AppConfigService(data_store=data_store, store=store)
    skill_runtime = SkillRuntimeService(store=store)

    def context_handler(request: SkillExecutionRequest) -> SkillExecutionResult:
        result = context_skill.execute(request.app_instance_id, ContextSkillRequest(**request.inputs))
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result)

    skill_runtime.register_handler("system.context", context_handler)
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
            id="bp.system.context",
            name="System Context",
            goal="exercise context skill",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.system.context",
                    "name": "context workflow",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "update", "kind": "skill", "ref": "system.context", "config": {"inputs": {"operation": "update", "current_goal": "new goal", "current_stage": "reasoning"}}},
                        {"id": "append", "kind": "skill", "ref": "system.context", "config": {"inputs": {"operation": "append", "section": "facts", "key": "fact-1", "value": {"summary": "hello"}, "tags": ["demo"]}}},
                        {"id": "get", "kind": "skill", "ref": "system.context", "config": {"inputs": {"operation": "get"}}},
                    ],
                }
            ],
            required_modules=[],
            required_skills=["system.context"],
        )
    )
    install_result = installer.install_app("bp.system.context", user_id="system-context-user")

    result = executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.system.context")

    assert result.status == "completed"
    assert result.steps[2].output["current_goal"] == "new goal"
    assert any(item["key"] == "fact-1" for item in result.steps[2].output["entries"])
    runtime_view = context_skill.execute(install_result.app_instance_id, ContextSkillRequest(operation="list_runtime_view"))
    assert runtime_view["context"]["app_instance_id"] == install_result.app_instance_id
    assert runtime_view["runtime"] is not None
