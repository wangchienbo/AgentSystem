from pathlib import Path

from app.models.app_blueprint import AppBlueprint
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.system_skill import SystemAuditRequest, SystemStateRequest
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
from app.services.system_skill_service import SystemAuditService, SystemStateService
from app.services.workflow_executor import WorkflowExecutorService


def test_system_state_and_audit_skills_execute_through_runtime(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "namespaces"), store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    app_config = AppConfigService(data_store=data_store, store=store)
    system_state = SystemStateService(data_store=data_store, store=store)
    system_audit = SystemAuditService(data_store=data_store, store=store)
    skill_runtime = SkillRuntimeService(store=store)

    def state_handler(request: SkillExecutionRequest) -> SkillExecutionResult:
        result = system_state.execute(request.app_instance_id, SystemStateRequest(**request.inputs))
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    def audit_handler(request: SkillExecutionRequest) -> SkillExecutionResult:
        result = system_audit.record(request.app_instance_id, SystemAuditRequest(**request.inputs))
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    skill_runtime.register_handler("system.state", state_handler)
    skill_runtime.register_handler("system.audit", audit_handler)
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
            id="bp.system.state.audit",
            name="System State Audit",
            goal="exercise state and audit skills",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.system.state.audit",
                    "name": "state audit",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.state", "kind": "skill", "ref": "system.state", "config": {"inputs": {"operation": "set", "key": "session", "value": {"status": "ready"}}}},
                        {"id": "get.state", "kind": "skill", "ref": "system.state", "config": {"inputs": {"operation": "get", "key": "session"}}},
                        {"id": "audit", "kind": "skill", "ref": "system.audit", "config": {"inputs": {"event_type": "state.checked", "detail": {"key": "session"}, "level": "info"}}},
                    ],
                }
            ],
            required_modules=[],
            required_skills=["system.state", "system.audit"],
        )
    )
    install_result = installer.install_app("bp.system.state.audit", user_id="system-state-audit-user")

    result = executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.system.state.audit")

    assert result.status == "completed"
    assert result.steps[1].output["value"]["status"] == "ready"
    assert system_state.execute(install_result.app_instance_id, SystemStateRequest(operation="get", key="session")).value["status"] == "ready"
    assert len(system_audit.list_records(install_result.app_instance_id)) == 1
