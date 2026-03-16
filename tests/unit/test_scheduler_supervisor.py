from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_instance import AppInstance
from app.models.scheduling import ScheduleRecord, SupervisionPolicy
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.scheduler import SchedulerError, SchedulerService
from app.services.supervisor import SupervisorError, SupervisorService


client = TestClient(app)


def build_instance() -> AppInstance:
    return AppInstance(
        id="app.ops.001",
        blueprint_id="bp.ops.001",
        owner_user_id="user.ops",
        status="installed",
        data_namespace="tenant/ops/app.ops.001",
    )


def test_scheduler_register_and_trigger_interval_schedule() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.ops.001")

    scheduler.register_schedule(
        ScheduleRecord(
            schedule_id="sch.interval.001",
            app_instance_id="app.ops.001",
            trigger_type="interval",
            task_name="sync cache",
            interval_seconds=60,
        )
    )

    results = scheduler.trigger_interval_schedules("app.ops.001")

    assert len(results) == 1
    assert results[0].triggered is True
    assert results[0].pending_tasks == ["sync cache"]


def test_scheduler_event_requires_event_name() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime)
    runtime.register_instance(build_instance())

    try:
        scheduler.register_schedule(
            ScheduleRecord(
                schedule_id="sch.event.001",
                app_instance_id="app.ops.001",
                trigger_type="event",
                task_name="process webhook",
            )
        )
    except SchedulerError as error:
        assert "event_name" in str(error)
    else:
        raise AssertionError("expected SchedulerError")


def test_supervisor_failure_and_restart_flow() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.ops.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.001",
            app_instance_id="app.ops.001",
            max_restart_attempts=2,
            open_circuit_after_failures=3,
        )
    )

    runtime.mark_failed("app.ops.001", reason="crash")
    observed = supervisor.observe_failure("app.ops.001", reason="crash")
    restarted = supervisor.attempt_restart("app.ops.001")

    assert observed.state == "restart_pending"
    assert restarted.restart_attempts == 1
    assert runtime.get_overview("app.ops.001").app_instance["status"] == "running"


def test_supervisor_opens_circuit_after_repeated_failures() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.ops.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.002",
            app_instance_id="app.ops.001",
            max_restart_attempts=5,
            open_circuit_after_failures=2,
        )
    )

    runtime.mark_failed("app.ops.001", reason="boom-1")
    supervisor.observe_failure("app.ops.001", reason="boom-1")
    runtime.stop("app.ops.001", reason="reset")
    runtime.start("app.ops.001", reason="resume")
    runtime.mark_failed("app.ops.001", reason="boom-2")
    observed = supervisor.observe_failure("app.ops.001", reason="boom-2")

    assert observed.state == "circuit_open"

    try:
        supervisor.attempt_restart("app.ops.001")
    except SupervisorError as error:
        assert "open circuit" in str(error)
    else:
        raise AssertionError("expected SupervisorError")


def test_scheduler_and_supervisor_api_flow() -> None:
    create_response = client.post(
        "/apps",
        json={
            "id": "app.api.ops.001",
            "blueprint_id": "bp.api.ops.001",
            "owner_user_id": "user.api",
            "status": "draft",
            "data_namespace": "tenant/api/app.api.ops.001",
        },
    )
    assert create_response.status_code == 200
    assert client.post("/apps/app.api.ops.001/actions/validate", json={}).status_code == 200
    assert client.post("/apps/app.api.ops.001/actions/compile", json={}).status_code == 200
    assert client.post("/apps/app.api.ops.001/actions/install", json={}).status_code == 200
    assert client.post("/apps/app.api.ops.001/actions/start", json={}).status_code == 200

    schedule_response = client.post(
        "/schedules",
        json={
            "schedule_id": "sch.api.001",
            "app_instance_id": "app.api.ops.001",
            "trigger_type": "interval",
            "task_name": "heartbeat sweep",
            "interval_seconds": 30,
        },
    )
    assert schedule_response.status_code == 200

    trigger_response = client.post(
        "/schedules/trigger/interval",
        json={"app_instance_id": "app.api.ops.001"},
    )
    assert trigger_response.status_code == 200
    assert trigger_response.json()[0]["pending_tasks"] == ["heartbeat sweep"]

    policy_response = client.post(
        "/supervision/policies",
        json={
            "policy_id": "sup.api.001",
            "app_instance_id": "app.api.ops.001",
            "max_restart_attempts": 2,
            "restart_on_failure": True,
            "open_circuit_after_failures": 3,
        },
    )
    assert policy_response.status_code == 200

    assert client.post("/apps/app.api.ops.001/actions/fail", json={"reason": "api crash"}).status_code == 200
    observe_response = client.post(
        "/supervision/app.api.ops.001/observe-failure",
        json={"reason": "api crash"},
    )
    assert observe_response.status_code == 200
    assert observe_response.json()["state"] == "restart_pending"

    restart_response = client.post("/supervision/app.api.ops.001/attempt-restart")
    assert restart_response.status_code == 200
    assert restart_response.json()["restart_attempts"] == 1
