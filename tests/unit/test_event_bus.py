from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_instance import AppInstance
from app.models.event_bus import EventSubscription
from app.models.scheduling import ScheduleRecord
from app.services.event_bus import EventBusService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService


client = TestClient(app)


def build_instance() -> AppInstance:
    return AppInstance(
        id="app.event.001",
        blueprint_id="bp.event.001",
        owner_user_id="user.event",
        status="installed",
        data_namespace="tenant/event/app.event.001",
    )


def test_event_bus_publish_triggers_event_schedule() -> None:
    store = RuntimeStateStore(base_dir="data/test-event-bus")
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    runtime.register_instance(build_instance())
    runtime.start("app.event.001")

    scheduler.register_schedule(
        ScheduleRecord(
            schedule_id="sch.event.trigger.001",
            app_instance_id="app.event.001",
            trigger_type="event",
            task_name="handle webhook",
            event_name="webhook.received",
        )
    )

    result = event_bus.publish(
        event_name="webhook.received",
        source="test",
        app_instance_id="app.event.001",
        payload={"kind": "demo"},
    )

    assert result.triggered_schedule_ids == ["sch.event.trigger.001"]
    assert result.triggered_app_ids == ["app.event.001"]
    assert runtime.get_overview("app.event.001").pending_tasks == ["handle webhook"]


def test_scheduler_creates_event_subscription_for_event_schedule() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime)
    runtime.register_instance(build_instance())

    scheduler.register_schedule(
        ScheduleRecord(
            schedule_id="sch.event.subscription.001",
            app_instance_id="app.event.001",
            trigger_type="event",
            task_name="sync external event",
            event_name="external.synced",
        )
    )

    subscriptions = scheduler.list_subscriptions("external.synced")
    assert len(subscriptions) == 1
    assert subscriptions[0].schedule_id == "sch.event.subscription.001"


def test_event_bus_api_flow() -> None:
    create_response = client.post(
        "/apps",
        json={
            "id": "app.api.event.001",
            "blueprint_id": "bp.api.event.001",
            "owner_user_id": "user.api",
            "status": "draft",
            "data_namespace": "tenant/api/app.api.event.001",
        },
    )
    assert create_response.status_code == 200
    assert client.post("/apps/app.api.event.001/actions/validate", json={}).status_code == 200
    assert client.post("/apps/app.api.event.001/actions/compile", json={}).status_code == 200
    assert client.post("/apps/app.api.event.001/actions/install", json={}).status_code == 200
    assert client.post("/apps/app.api.event.001/actions/start", json={}).status_code == 200

    schedule_response = client.post(
        "/schedules",
        json={
            "schedule_id": "sch.api.event.001",
            "app_instance_id": "app.api.event.001",
            "trigger_type": "event",
            "task_name": "process event",
            "event_name": "app.updated",
        },
    )
    assert schedule_response.status_code == 200

    publish_response = client.post(
        "/events/publish",
        json={
            "event_name": "app.updated",
            "source": "api-test",
            "app_instance_id": "app.api.event.001",
            "payload": {"version": "1.0.1"},
        },
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["triggered_schedule_ids"] == ["sch.api.event.001"]

    event_log_response = client.get("/events", params={"event_name": "app.updated"})
    assert event_log_response.status_code == 200
    assert event_log_response.json()[0]["source"] == "api-test"

    subscriptions_response = client.get("/events/subscriptions", params={"event_name": "app.updated"})
    assert subscriptions_response.status_code == 200
    assert subscriptions_response.json()[0]["schedule_id"] == "sch.api.event.001"


def test_manual_subscription_api() -> None:
    response = client.post(
        "/events/subscriptions",
        json={
            "subscription_id": "sub.manual.001",
            "event_name": "manual.event",
            "app_instance_id": "app.manual.001",
        },
    )
    assert response.status_code == 200
    assert response.json()["event_name"] == "manual.event"
