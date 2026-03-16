from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_instance import AppInstance
from app.services.lifecycle import AppLifecycleService, LifecycleError
from app.services.runtime_host import AppRuntimeHostService


client = TestClient(app)


def build_instance(status: str = "draft") -> AppInstance:
    return AppInstance(
        id="app.demo.001",
        blueprint_id="bp.demo.001",
        owner_user_id="user.demo",
        status=status,
        data_namespace="tenant/demo/app.demo.001",
    )


def test_lifecycle_valid_transitions() -> None:
    service = AppLifecycleService()
    service.register_instance(build_instance())

    service.transition("app.demo.001", "validate")
    service.transition("app.demo.001", "compile")
    result = service.transition("app.demo.001", "install")

    assert result.current_status == "installed"
    assert len(service.list_events("app.demo.001")) == 3


def test_lifecycle_rejects_invalid_transition() -> None:
    service = AppLifecycleService()
    service.register_instance(build_instance())

    try:
        service.transition("app.demo.001", "start")
    except LifecycleError as error:
        assert "Invalid lifecycle transition" in str(error)
    else:
        raise AssertionError("expected LifecycleError")


def test_runtime_host_start_pause_resume_stop() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    runtime.register_instance(build_instance(status="installed"))

    runtime.start("app.demo.001", reason="boot")
    runtime.pause("app.demo.001", reason="maintenance")
    overview = runtime.resume("app.demo.001", reason="resume ops")
    stopped = runtime.stop("app.demo.001", reason="shutdown")

    assert overview.lease is not None
    assert overview.lease.health == "healthy"
    assert stopped.app_instance["status"] == "stopped"


def test_runtime_host_healthcheck_and_task_queue() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    runtime.register_instance(build_instance(status="installed"))
    runtime.start("app.demo.001")

    tasks = runtime.enqueue_task("app.demo.001", "sync inbox")
    lease = runtime.healthcheck("app.demo.001", healthy=False)
    overview = runtime.get_overview("app.demo.001")

    assert tasks == ["sync inbox"]
    assert lease.restart_count == 1
    assert overview.pending_tasks == ["sync inbox"]
    assert overview.latest_checkpoint is not None


def test_app_runtime_api_flow() -> None:
    create_response = client.post(
        "/apps",
        json={
            "id": "app.api.001",
            "blueprint_id": "bp.api.001",
            "owner_user_id": "user.api",
            "status": "draft",
            "data_namespace": "tenant/api/app.api.001",
        },
    )
    assert create_response.status_code == 200

    assert client.post("/apps/app.api.001/actions/validate", json={}).status_code == 200
    assert client.post("/apps/app.api.001/actions/compile", json={}).status_code == 200
    assert client.post("/apps/app.api.001/actions/install", json={}).status_code == 200

    start_response = client.post(
        "/apps/app.api.001/actions/start",
        json={"reason": "boot app"},
    )
    assert start_response.status_code == 200
    assert start_response.json()["app_instance"]["status"] == "running"

    task_response = client.post(
        "/apps/app.api.001/tasks",
        json={"task_name": "poll queue"},
    )
    assert task_response.status_code == 200
    assert task_response.json()["pending_tasks"] == ["poll queue"]

    runtime_response = client.get("/apps/app.api.001/runtime")
    assert runtime_response.status_code == 200
    assert runtime_response.json()["latest_checkpoint"] is not None


def test_unknown_app_returns_404() -> None:
    response = client.get("/apps/unknown.app")
    assert response.status_code == 404


def test_invalid_start_transition_returns_400() -> None:
    client.post(
        "/apps",
        json={
            "id": "app.api.002",
            "blueprint_id": "bp.api.002",
            "owner_user_id": "user.api",
            "status": "draft",
            "data_namespace": "tenant/api/app.api.002",
        },
    )

    response = client.post("/apps/app.api.002/actions/start", json={})
    assert response.status_code == 400
