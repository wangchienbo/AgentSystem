from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.workflow_subscription import WorkflowEventSubscription
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
from app.services.workflow_subscription import WorkflowSubscriptionService


client = TestClient(app)


def test_workflow_subscription_triggers_execution_on_event(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "workflow-subscription-store"))
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "workflow-subscription-ns"), store=store)
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
    subscription_service = WorkflowSubscriptionService(workflow_executor=executor, store=store)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.workflow.subscription",
            name="Workflow Subscription App",
            goal="run workflow from event",
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": "wf.event",
                    "name": "event flow",
                    "triggers": ["event"],
                    "steps": [
                        {"id": "set.event", "kind": "module", "ref": "state.set", "config": {"key": "event-payload", "value": {"$from_inputs": "payload"}}},
                    ],
                }
            ],
            required_modules=["state.set"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.workflow.subscription", user_id="workflow-sub-user")

    subscription_service.subscribe(
        WorkflowEventSubscription(
            subscription_id="wfsub.001",
            event_name="demo.event",
            app_instance_id=install_result.app_instance_id,
            workflow_id="wf.event",
        )
    )

    executions = subscription_service.trigger("demo.event", payload={"payload": {"source": "event"}})

    assert len(executions) == 1
    assert executions[0].workflow_id == "wf.event"
    records = data_store.list_records(f"{install_result.app_instance_id}:app_data")
    event_record = next(item for item in records if item.key == "event-payload")
    assert event_record.value["source"] == "event"


def test_workflow_subscription_api_flow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.workflow.subscription.api",
            "name": "Workflow Subscription API App",
            "goal": "run workflow from published event",
            "roles": [],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.event.api",
                    "name": "event api flow",
                    "triggers": ["event"],
                    "steps": [
                        {"id": "set.payload", "kind": "module", "ref": "state.set", "config": {"key": "event-api-payload", "value": {"$from_inputs": "payload"}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": ["state.set"],
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
        "/registry/apps/bp.workflow.subscription.api/install",
        json={"user_id": "workflow-sub-api-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    subscribe_response = client.post(
        "/workflow-subscriptions",
        json={
            "subscription_id": "wfsub.api.001",
            "event_name": "workflow.api.event",
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.event.api"
        },
    )
    assert subscribe_response.status_code == 200

    publish_response = client.post(
        "/events/publish",
        json={
            "event_name": "workflow.api.event",
            "source": "api-test",
            "app_instance_id": app_instance_id,
            "payload": {"payload": {"kind": "api"}},
        },
    )
    assert publish_response.status_code == 200
    assert len(publish_response.json()["workflow_runs"]) == 1
    assert publish_response.json()["workflow_runs"][0]["workflow_id"] == "wf.event.api"

    records_response = client.get(f"/data/namespaces/{app_instance_id}:app_data/records")
    assert records_response.status_code == 200
    assert any(item["key"] == "event-api-payload" for item in records_response.json())
