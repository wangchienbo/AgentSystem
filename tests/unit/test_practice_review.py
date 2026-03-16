from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.practice_review import PracticeReviewRequest
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.experience_store import ExperienceStore
from app.services.lifecycle import AppLifecycleService
from app.services.practice_review import PracticeReviewService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService


client = TestClient(app)


def test_practice_review_generates_experience() -> None:
    store = RuntimeStateStore(base_dir="data/test-practice-review")
    data_store = AppDataStore(base_dir="data/test-practice-review-ns", store=store)
    experience_store = ExperienceStore()
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    registry = AppRegistryService(store=store)
    installer = AppInstallerService(registry=registry, lifecycle=lifecycle, runtime_host=runtime, data_store=data_store)
    review_service = PracticeReviewService(event_bus=event_bus, data_store=data_store, experience_store=experience_store)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.practice.review",
            name="Practice Review App",
            goal="review runtime practice",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.review", "name": "review", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
        )
    )
    install_result = installer.install_app("bp.practice.review", user_id="user.review")
    app_instance_id = install_result.app_instance_id

    event_bus.publish("task.completed", source="test", app_instance_id=app_instance_id, payload={"ok": True})
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="summary",
        value={"result": "success"},
        tags=["result"],
    )

    result = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))

    assert result.event_count == 1
    assert result.record_count >= 1
    assert result.experience.source == "runtime"
    assert "task.completed" in result.experience.summary
    assert len(experience_store.list_experiences()) == 1


def test_practice_review_api_flow() -> None:
    install_response = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "review-api-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    publish_response = client.post(
        "/events/publish",
        json={
            "event_name": "assistant.responded",
            "source": "api-test",
            "app_instance_id": app_instance_id,
            "payload": {"kind": "reply"},
        },
    )
    assert publish_response.status_code == 200

    namespaces_response = client.get("/data/namespaces", params={"app_instance_id": app_instance_id})
    app_data_namespace = next(item for item in namespaces_response.json() if item["namespace_type"] == "app_data")
    record_response = client.post(
        f"/data/namespaces/{app_data_namespace['namespace_id']}/records",
        json={"key": "reply-log", "value": {"status": "ok"}, "tags": ["reply"]},
    )
    assert record_response.status_code == 200

    review_response = client.post(
        "/practice/review",
        json={"app_instance_id": app_instance_id},
    )
    assert review_response.status_code == 200
    assert review_response.json()["experience"]["source"] == "runtime"
    assert review_response.json()["event_count"] >= 1
