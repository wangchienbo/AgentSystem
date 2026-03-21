from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.patch_proposal import SelfRefinementRequest
from app.models.practice_review import PracticeReviewRequest
from app.models.proposal_review import ProposalReviewRequest
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.experience_store import ExperienceStore
from app.services.lifecycle import AppLifecycleService
from app.services.practice_review import PracticeReviewService
from app.services.proposal_review import ProposalReviewService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.self_refinement import SelfRefinementService


client = TestClient(app)


def test_proposal_review_apply_low_risk_runtime_patch(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "proposal-review-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "proposal-review-ns"), store=store)
    experience_store = ExperienceStore()
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime, store=store)
    event_bus = EventBusService(scheduler=scheduler, store=store)
    registry = AppRegistryService(store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store, runtime_host=runtime)
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        context_store=context_store,
    )
    review_service = PracticeReviewService(
        event_bus=event_bus,
        data_store=data_store,
        experience_store=experience_store,
        context_store=context_store,
    )
    refinement_service = SelfRefinementService(
        experience_store=experience_store,
        registry=registry,
        lifecycle=lifecycle,
        context_store=context_store,
    )
    proposal_service = ProposalReviewService(lifecycle=lifecycle, store=store, context_store=context_store)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.proposal.review",
            name="Proposal Review App",
            goal="review proposals",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.review", "name": "review", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install_result = installer.install_app("bp.proposal.review", user_id="user.review")
    app_instance_id = install_result.app_instance_id

    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="decisions",
        key="review-policy",
        value={"mode": "careful"},
        tags=["policy"],
    )
    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="review-log",
        value={"status": "needs refinement"},
        tags=["review"],
    )
    practice = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))
    proposals = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=app_instance_id, experience_id=practice.experience.experience_id)
    )
    proposal_service.register_proposals(proposals)

    runtime_proposal = next(item for item in proposal_service.list_proposals(app_instance_id) if item.target_type == "runtime_policy")
    review = proposal_service.review(
        ProposalReviewRequest(proposal_id=runtime_proposal.proposal_id, action="apply", reviewer="tester")
    )

    assert review.status == "applied"
    assert review.context_entry_count >= 1
    assert "context_goal=" in review.note or "context_stage=" in review.note or "context_entries=" in review.note
    assert lifecycle.get_instance(app_instance_id).runtime_policy.idle_strategy == "keep_alive"


def test_proposal_review_api_flow() -> None:
    install_response = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "proposal-review-user"},
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
    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "open_loops", "key": "proposal-followup", "value": {"needed": True}, "tags": ["followup"]},
    )
    review_response = client.post("/practice/review", json={"app_instance_id": app_instance_id})
    experience_id = review_response.json()["experience"]["experience_id"]

    proposal_response = client.post(
        "/self-refinement/propose",
        json={"app_instance_id": app_instance_id, "experience_id": experience_id},
    )
    assert proposal_response.status_code == 200

    list_response = client.get("/self-refinement/proposals", params={"app_instance_id": app_instance_id})
    assert list_response.status_code == 200
    assert len(list_response.json()) >= 1

    workflow_proposal = next(item for item in list_response.json() if item["target_type"] == "workflow")
    approve_response = client.post(
        "/self-refinement/review",
        json={"proposal_id": workflow_proposal["proposal_id"], "action": "approve", "reviewer": "human", "note": "looks good"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert approve_response.json()["context_entry_count"] >= 1
    assert "context_entries=" in approve_response.json()["note"]
