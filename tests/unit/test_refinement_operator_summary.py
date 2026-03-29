from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.patch_proposal import SelfRefinementRequest
from app.models.practice_review import PracticeReviewRequest
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.event_bus import EventBusService
from app.services.experience_store import ExperienceStore
from app.services.lifecycle import AppLifecycleService
from app.services.practice_review import PracticeReviewService
from app.models.priority_analysis import PriorityAnalysisRequest
from app.services.priority_analysis import PriorityAnalysisService
from app.services.proposal_review import ProposalReviewService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.self_refinement import SelfRefinementService
from app.services.refinement_memory import RefinementMemoryStore


client = TestClient(app)


def test_refinement_operator_summary_aggregates_priority_review_and_governance(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "refinement-operator-summary-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "refinement-operator-summary-ns"), store=store)
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
    memory = RefinementMemoryStore(store=store)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.refinement.operator.summary",
            name="Refinement Operator Summary App",
            goal="summarize refinement operator state",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.operator.summary", "name": "summary", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install = installer.install_app("bp.refinement.operator.summary", user_id="operator-user")
    app_instance_id = install.app_instance_id

    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="open_loops",
        key="operator-followup",
        value={"needed": True},
        tags=["operator"],
    )
    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="operator-log",
        value={"status": "needs refinement"},
        tags=["operator"],
    )
    review = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))
    proposals = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id)
    )
    proposal_service.register_proposals(proposals)
    priority = analyzer.analyze(PriorityAnalysisRequest(app_instance_id=app_instance_id))

    summary = memory.build_operator_summary(
        app_instance_id=app_instance_id,
        proposals=proposal_service.list_proposals(app_instance_id),
        reviews=proposal_service.list_reviews(),
        priority=priority,
        recent_limit=3,
    )

    assert summary.app_instance_id == app_instance_id
    assert summary.proposal_count >= 1
    assert summary.proposed_review_count >= 1
    assert summary.latest_priority is not None
    assert summary.primary_contradiction
    assert summary.recommended_action
    assert summary.governance.overview.app_instance_id == app_instance_id


def test_refinement_operator_summary_api_surface() -> None:
    response = client.get("/self-refinement/operator-summary", params={"app_instance_id": "app.missing", "recent_limit": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["app_instance_id"] == "app.missing"
    assert payload["proposal_count"] >= 0
    assert payload["governance"]["overview"]["app_instance_id"] == "app.missing"
