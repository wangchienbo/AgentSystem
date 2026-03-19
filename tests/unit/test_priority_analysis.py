from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.patch_proposal import SelfRefinementRequest
from app.models.practice_review import PracticeReviewRequest
from app.models.priority_analysis import PriorityAnalysisRequest
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.experience_store import ExperienceStore
from app.services.lifecycle import AppLifecycleService
from app.services.practice_review import PracticeReviewService
from app.services.priority_analysis import PriorityAnalysisService
from app.services.proposal_review import ProposalReviewService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.self_refinement import SelfRefinementService


client = TestClient(app)


def test_priority_analysis_ranks_runtime_policy_first_when_low_risk(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "priority-analysis-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "priority-analysis-ns"), store=store)
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
    analyzer = PriorityAnalysisService(proposal_review=proposal_service, context_store=context_store)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.priority.analysis",
            name="Priority Analysis App",
            goal="rank proposals",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.priority", "name": "priority", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install_result = installer.install_app("bp.priority.analysis", user_id="user.priority")
    app_instance_id = install_result.app_instance_id

    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="open_loops",
        key="priority-followup",
        value={"needed": True},
        tags=["followup"],
    )
    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="decisions",
        key="prioritize-closure",
        value={"enabled": True},
        tags=["decision"],
    )
    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="priority-log",
        value={"status": "needs optimization"},
        tags=["priority"],
    )
    practice = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))
    proposals = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=app_instance_id, experience_id=practice.experience.experience_id)
    )
    proposal_service.register_proposals(proposals)

    result = analyzer.analyze(PriorityAnalysisRequest(app_instance_id=app_instance_id))

    assert result.prioritized[0].rank == 1
    assert "主要矛盾" in result.primary_contradiction
    assert result.context_summary
    top_proposal_id = result.prioritized[0].proposal_id
    top_proposal = next(item for item in proposal_service.list_proposals(app_instance_id) if item.proposal_id == top_proposal_id)
    assert top_proposal.target_type in {"workflow", "runtime_policy"}
    workflow_priority = next(item for item in result.prioritized if "workflow" in item.proposal_id)
    assert "open_loops" in workflow_priority.context_signals


def test_priority_analysis_api_flow() -> None:
    install_response = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "priority-api-user"},
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
        json={"section": "open_loops", "key": "priority-api-followup", "value": {"needed": True}, "tags": ["followup"]},
    )
    review_response = client.post("/practice/review", json={"app_instance_id": app_instance_id})
    experience_id = review_response.json()["experience"]["experience_id"]
    client.post(
        "/self-refinement/propose",
        json={"app_instance_id": app_instance_id, "experience_id": experience_id},
    )

    analysis_response = client.post(
        "/self-refinement/analyze-priority",
        json={"app_instance_id": app_instance_id},
    )
    assert analysis_response.status_code == 200
    assert len(analysis_response.json()["prioritized"]) >= 1
    assert analysis_response.json()["recommended_action"]
    assert analysis_response.json()["context_summary"]
    assert isinstance(analysis_response.json()["prioritized"][0]["context_signals"], list)
