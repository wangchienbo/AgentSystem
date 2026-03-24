from app.models.app_blueprint import AppBlueprint
from app.services.app_catalog import AppCatalogService
from app.models.interaction import AppCatalogEntry, UserCommand
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.interaction_gateway import InteractionGateway
from app.services.lifecycle import AppLifecycleService
from app.services.requirement_router import RequirementRouter
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.workflow_executor import WorkflowExecutorService
from app.services.workflow_observability import WorkflowObservabilityService


def _build_runtime(prefix: str):
    store = RuntimeStateStore(base_dir=f"/tmp/{prefix}-store")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=f"/tmp/{prefix}-ns", store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    executor = WorkflowExecutorService(
        registry=registry,
        lifecycle=lifecycle,
        data_store=data_store,
        event_bus=event_bus,
        context_store=context_store,
    )
    observability = WorkflowObservabilityService(workflow_executor=executor)
    catalog = AppCatalogService()
    gateway = InteractionGateway(catalog, RequirementRouter(), lifecycle, runtime, installer, context_store)
    return registry, catalog, gateway, lifecycle, executor, observability



def test_golden_path_register_install_interact_execute_retry_and_observe() -> None:
    registry, catalog, gateway, lifecycle, executor, observability = _build_runtime("golden-path")

    registry.register_blueprint(
        AppBlueprint(
            id="bp.golden.path",
            name="Golden Path App",
            goal="exercise the primary operator path",
            roles=[{"id": "r1", "name": "agent", "type": "agent"}],
            tasks=[],
            workflows=[
                {
                    "id": "wf.golden",
                    "name": "golden",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.input", "kind": "module", "ref": "state.set", "config": {"key": "golden.input", "value": {"token": {"$from_inputs": "token", "default": "missing"}}}},
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
                }
            ],
            required_modules=["state.set"],
            required_skills=[],
            runtime_policy={"execution_mode": "service"},
        )
    )
    catalog.register(
        AppCatalogEntry(
            app_id="app.golden.path",
            name="Golden Path",
            description="exercise operator golden path",
            execution_mode="service",
            trigger_phrases=["打开黄金路径"],
            blueprint_id="bp.golden.path",
        )
    )

    decision = gateway.handle_command(UserCommand(user_id="gold-user", text="请打开黄金路径"))
    assert decision.action == "open_app"
    assert decision.app_instance_id == "app.golden.path:gold-user"
    assert lifecycle.get_instance(decision.app_instance_id).status == "running"

    execution = executor.execute_workflow(
        app_instance_id=decision.app_instance_id,
        workflow_id="wf.golden",
        trigger="manual",
        inputs={"token": "golden-token"},
    )
    assert execution.status == "partial"
    assert execution.failed_step_ids == ["blocked.skill"]
    assert execution.outputs["inputs"]["token"] == "golden-token"

    retried = executor.retry_last_failure(decision.app_instance_id)
    assert retried.trigger == "retry:manual"
    assert retried.status == "partial"
    assert retried.retry_comparison is not None
    assert retried.retry_comparison.previous_failed_step_ids == ["blocked.skill"]
    assert retried.retry_comparison.unchanged_failed_step_ids == ["blocked.skill"]

    diagnostics = observability.get_diagnostics_summary(
        app_instance_id=decision.app_instance_id,
        workflow_id="wf.golden",
        failed_step_id="blocked.skill",
    )
    assert diagnostics.latest_execution is not None
    assert diagnostics.latest_failure is not None
    assert diagnostics.latest_retry is not None

    overview = observability.get_overview(
        app_instance_id=decision.app_instance_id,
        workflow_id="wf.golden",
        failed_step_id="blocked.skill",
    )
    assert overview.health.health_status == "failing"
    assert overview.health.unresolved_failure_count == 1

    dashboard = observability.get_dashboard_summary(
        app_instance_id=decision.app_instance_id,
        workflow_id="wf.golden",
        failed_step_id="blocked.skill",
        timeline_limit=2,
    )
    assert dashboard.stats.total_executions >= 2
    assert dashboard.stats.total_failures >= 1
    assert dashboard.stats.total_retries >= 1
    assert dashboard.recent_timeline.meta.returned_count >= 1
    assert len(dashboard.recent_timeline.items) >= 1
