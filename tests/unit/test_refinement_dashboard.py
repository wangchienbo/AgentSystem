from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.patch_proposal import SelfRefinementRequest
from app.models.practice_review import PracticeReviewRequest
from app.models.refinement_loop import RefinementLoopRequest
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
from app.services.refinement_loop import RefinementLoopService
from app.services.refinement_memory import RefinementMemoryStore
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.self_refinement import SelfRefinementService


client = TestClient(app)


class StubCompletedProcess:
    def __init__(self, returncode: int = 1, stdout: str = "failed", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def failing_verification_executor(_runner_path: str) -> StubCompletedProcess:
    return StubCompletedProcess(returncode=1, stdout="grouped regression failed")


def test_refinement_dashboard_tracks_failed_hypothesis_archive(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "refinement-dashboard-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "refinement-dashboard-ns"), store=store)
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
    loop = RefinementLoopService(
        proposal_review=proposal_service,
        priority_analysis=analyzer,
        memory=memory,
        verification_executor=failing_verification_executor,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.refinement.dashboard",
            name="Refinement Dashboard App",
            goal="track failed hypotheses and dashboard history",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.dashboard", "name": "dashboard", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install = installer.install_app("bp.refinement.dashboard", user_id="dashboard-user")
    app_instance_id = install.app_instance_id

    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="open_loops",
        key="dashboard-followup",
        value={"needed": True},
        tags=["dashboard"],
    )
    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="dashboard-log",
        value={"status": "keep learning"},
        tags=["dashboard"],
    )
    review = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))
    proposals = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id)
    )
    proposal_service.register_proposals(proposals)
    loop.run(RefinementLoopRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id))

    overview = memory.build_overview(app_instance_id)
    dashboard = memory.build_dashboard(app_instance_id, limit=3)
    failed = memory.list_failed_hypotheses(app_instance_id=app_instance_id)

    assert overview.failed_hypothesis_count >= 1
    assert overview.latest_failed_hypothesis is not None
    assert dashboard.overview.failed_hypothesis_count >= 1
    assert dashboard.recent_failed_hypotheses
    assert failed[0].app_instance_id == app_instance_id
    assert dashboard.recent_hypotheses[0].repeat_risk in {"low", "medium", "high"}


def test_refinement_dashboard_api_surface() -> None:
    dashboard_response = client.get("/self-refinement/dashboard", params={"app_instance_id": "app.missing", "limit": 3})
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["overview"]["app_instance_id"] == "app.missing"
    assert isinstance(dashboard["recent_hypotheses"], list)

    failed_response = client.get("/self-refinement/failed-hypotheses", params={"app_instance_id": "app.missing"})
    assert failed_response.status_code == 200
    assert isinstance(failed_response.json(), list)
