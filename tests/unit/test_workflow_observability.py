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
from app.services.workflow_observability import WorkflowObservabilityService


def _build_runtime(prefix: str):
    tmp_path = Path("/tmp")
    store = RuntimeStateStore(base_dir=str(tmp_path / f"{prefix}-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / f"{prefix}-ns"), store=store)
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
    observability = WorkflowObservabilityService(workflow_executor=executor)
    return registry, installer, executor, observability


def test_workflow_observability_reports_failing_health_for_failed_step_path() -> None:
    registry, installer, executor, observability = _build_runtime("workflow-observability-failing")

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.obs.failing",
            name="Workflow Observability Failing App",
            goal="report failing state",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.obs.failing",
                    "name": "obs failing",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
                    ],
                }
            ],
            required_modules=[],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.obs.failing", user_id="obs-failing-user")
    executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.obs.failing")
    executor.retry_last_failure(install_result.app_instance_id)

    overview = observability.get_overview(
        app_instance_id=install_result.app_instance_id,
        workflow_id="wf.obs.failing",
        failed_step_id="blocked.skill",
    )

    assert overview.diagnostics.latest_failure is not None
    assert overview.latest_recovery is not None
    assert overview.health.health_status == "failing"
    assert overview.health.severity == "critical"
    assert overview.health.unresolved_failure_count == 1
    assert overview.health.latest_failed_step_ids == ["blocked.skill"]
    assert overview.health.has_recent_retry is True
    assert overview.health.last_transition == "failure->retry-partial"


def test_workflow_observability_reports_recovering_state_after_resolved_retry() -> None:
    registry, installer, executor, observability = _build_runtime("workflow-observability-recovering")

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.obs.recovering",
            name="Workflow Observability Recovering App",
            goal="report recovering state",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.obs.recovering",
                    "name": "obs recovering",
                    "triggers": ["manual"],
                    "steps": [
                        {
                            "id": "set.maybe",
                            "kind": "module",
                            "ref": "state.set",
                            "config": {
                                "key": "maybe",
                                "value": {"ok": True},
                                "when": {"source": {"$from_inputs": "allow_write", "default": False}, "equals": True},
                            },
                        },
                        {
                            "id": "blocked.skill",
                            "kind": "skill",
                            "ref": "skill.blocked",
                            "config": {
                                "mode": {"$from_inputs": "skill_mode", "default": "fail"},
                            },
                        },
                    ],
                }
            ],
            required_modules=["state.set"],
            required_skills=["skill.blocked"],
        )
    )
    install_result = installer.install_app("bp.workflow.obs.recovering", user_id="obs-recovering-user")

    executor.execute_workflow(
        install_result.app_instance_id,
        workflow_id="wf.obs.recovering",
        inputs={"allow_write": False, "skill_mode": "fail"},
    )
    executor.retry_last_failure(install_result.app_instance_id)

    history = executor.list_history(install_result.app_instance_id)
    history[-1].status = "completed"
    history[-1].failed_step_ids = []
    history[-1].retry_comparison.retried_status = "completed"
    history[-1].retry_comparison.retried_failed_step_ids = []
    history[-1].retry_comparison.resolved_failed_step_ids = ["blocked.skill"]
    history[-1].retry_comparison.unchanged_failed_step_ids = []
    history[-1].retry_comparison.newly_failed_step_ids = []

    overview = observability.get_overview(
        app_instance_id=install_result.app_instance_id,
        workflow_id="wf.obs.recovering",
        failed_step_id="blocked.skill",
    )

    assert overview.latest_recovery is not None
    assert overview.latest_recovery.recovered is True
    assert overview.latest_recovery.resolved_failed_step_ids == ["blocked.skill"]
    assert overview.health.health_status == "recovering"
    assert overview.health.severity == "warning"
    assert overview.health.unresolved_failure_count == 0
    assert overview.health.latest_failed_step_ids == []
    assert overview.health.has_recent_retry is True
    assert overview.health.last_transition == "failure->recovered"



def test_workflow_observability_reports_healthy_and_unknown_states() -> None:
    registry, installer, executor, observability = _build_runtime("workflow-observability-states")

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.obs.states",
            name="Workflow Observability States App",
            goal="report healthy and unknown states",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.obs.healthy",
                    "name": "obs healthy",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "set.ok", "kind": "module", "ref": "state.set", "config": {"key": "ok", "value": {"done": True}}},
                    ],
                },
                {
                    "id": "wf.obs.unknown",
                    "name": "obs unknown",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "read.missing", "kind": "module", "ref": "state.get", "config": {"key": "missing"}},
                    ],
                },
            ],
            required_modules=["state.set", "state.get"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.obs.states", user_id="obs-states-user")

    executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.obs.healthy")
    healthy = observability.get_health_summary(install_result.app_instance_id, workflow_id="wf.obs.healthy")
    assert healthy.health_status == "healthy"
    assert healthy.severity == "info"
    assert healthy.unresolved_failure_count == 0
    assert healthy.latest_failed_step_ids == []
    assert healthy.has_recent_retry is False
    assert healthy.last_transition == "completed"

    executor.execute_workflow(install_result.app_instance_id, workflow_id="wf.obs.unknown")
    unknown = observability.get_health_summary(install_result.app_instance_id, workflow_id="wf.obs.unknown")
    assert unknown.health_status == "unknown"
    assert unknown.severity == "info"
    assert unknown.unresolved_failure_count == 0
    assert unknown.latest_failed_step_ids == []
    assert unknown.has_recent_retry is False
    assert unknown.last_transition == "partial-without-failed-steps"
