from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.patch_proposal import SelfRefinementRequest
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
from app.services.self_refinement import SelfRefinementService


client = TestClient(app)


def test_self_refinement_generates_patch_proposals() -> None:
    store = RuntimeStateStore(base_dir="data/test-self-refinement")
    data_store = AppDataStore(base_dir="data/test-self-refinement-ns", store=store)
    experience_store = ExperienceStore()
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    registry = AppRegistryService(store=store)
    installer = AppInstallerService(registry=registry, lifecycle=lifecycle, runtime_host=runtime, data_store=data_store)
    review_service = PracticeReviewService(event_bus=event_bus, data_store=data_store, experience_store=experience_store)
    refinement_service = SelfRefinementService(experience_store=experience_store, registry=registry, lifecycle=lifecycle)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.self.refinement",
            name="Self Refinement App",
            goal="generate refinement proposals",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.self", "name": "self", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install_result = installer.install_app("bp.self.refinement", user_id="user.refine")
    app_instance_id = install_result.app_instance_id

    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="review-log",
        value={"status": "needs refinement"},
        tags=["review"],
    )
    review_result = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))

    result = refinement_service.propose(
        SelfRefinementRequest(
            app_instance_id=app_instance_id,
            experience_id=review_result.experience.experience_id,
        )
    )

    assert len(result.proposals) >= 2
    assert any(item.target_type == "runtime_policy" for item in result.proposals)
    assert any(item.target_type == "workflow" for item in result.proposals)


def test_self_refinement_api_flow() -> None:
    install_response = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "self-refine-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    client.post(
        "/events/publish",
        json={
            "event_name": "assistant.responded",
            "source": "api-test",
            "app_instance_id": app_instance_id,
            "payload": {"kind": "reply"},
        },
    )
    namespaces_response = client.get("/data/namespaces", params={"app_instance_id": app_instance_id})
    app_data_namespace = next(item for item in namespaces_response.json() if item["namespace_type"] == "app_data")
    client.post(
        f"/data/namespaces/{app_data_namespace['namespace_id']}/records",
        json={"key": "reply-log", "value": {"status": "ok"}, "tags": ["reply"]},
    )
    review_response = client.post(
        "/practice/review",
        json={"app_instance_id": app_instance_id},
    )
    experience_id = review_response.json()["experience"]["experience_id"]

    proposal_response = client.post(
        "/self-refinement/propose",
        json={"app_instance_id": app_instance_id, "experience_id": experience_id},
    )
    assert proposal_response.status_code == 200
    assert len(proposal_response.json()["proposals"]) >= 1
    assert proposal_response.json()["proposals"][0]["risk_level"] in {"low", "medium", "high"}
