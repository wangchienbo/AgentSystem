import os
from pathlib import Path

os.environ.pop("AGENTSYSTEM_DISABLE_REFINEMENT_GROUPED_REGRESSION", None)

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.patch_proposal import SelfRefinementRequest
from app.models.practice_review import PracticeReviewRequest
from app.models.refinement_loop import RefinementFilter, RefinementLoopRequest
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
from app.services.refinement_rollout import RefinementRolloutService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.self_refinement import SelfRefinementService


client = TestClient(app)


class StubCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def stub_verification_executor(_runner_path: str) -> StubCompletedProcess:
    return StubCompletedProcess(returncode=0, stdout="grouped regression passed")


def failing_verification_executor(_runner_path: str) -> StubCompletedProcess:
    return StubCompletedProcess(returncode=1, stdout="grouped regression failed")


def _build_services(tmp_path: Path, failing: bool = False):
    store = RuntimeStateStore(base_dir=str(tmp_path / "refinement-filter-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "refinement-filter-ns"), store=store)
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
        verification_executor=failing_verification_executor if failing else stub_verification_executor,
    )
    rollout = RefinementRolloutService(memory=memory, proposal_review=proposal_service)
    return {
        "store": store,
        "data_store": data_store,
        "event_bus": event_bus,
        "registry": registry,
        "context_store": context_store,
        "installer": installer,
        "review_service": review_service,
        "refinement_service": refinement_service,
        "proposal_service": proposal_service,
        "memory": memory,
        "loop": loop,
        "rollout": rollout,
    }


def _seed_refinement_run(tmp_path: Path, failing: bool = False):
    services = _build_services(tmp_path, failing=failing)
    registry = services["registry"]
    installer = services["installer"]
    context_store = services["context_store"]
    event_bus = services["event_bus"]
    data_store = services["data_store"]
    review_service = services["review_service"]
    refinement_service = services["refinement_service"]
    proposal_service = services["proposal_service"]
    loop = services["loop"]

    blueprint_id = "bp.refinement.filter.fail" if failing else "bp.refinement.filter.pass"
    registry.register_blueprint(
        AppBlueprint(
            id=blueprint_id,
            name="Refinement Filter App",
            goal="exercise refinement filters and stats",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.filter", "name": "filter", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install = installer.install_app(blueprint_id, user_id="filter-user")
    app_instance_id = install.app_instance_id

    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="open_loops",
        key="filter-followup",
        value={"needed": True},
        tags=["filter"],
    )
    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="filter-log",
        value={"status": "needs refinement"},
        tags=["filter"],
    )
    review = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))
    proposals = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id)
    )
    proposal_service.register_proposals(proposals)
    result = loop.run(RefinementLoopRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id))
    return services, app_instance_id, result


def test_refinement_memory_filter_pages_and_stats(tmp_path: Path) -> None:
    services, app_instance_id, result = _seed_refinement_run(tmp_path, failing=False)
    memory = services["memory"]
    rollout = services["rollout"]

    queue_item = result.queue_item
    assert queue_item is not None
    transitioned = rollout.transition(queue_item.queue_id, "rollback" if queue_item.status == "applied" else "approve")

    queue_page = memory.list_queue_page(
        RefinementFilter(app_instance_id=app_instance_id, proposal_id=queue_item.proposal_id, limit=5)
    )
    stats = memory.get_stats_summary(RefinementFilter(app_instance_id=app_instance_id))
    approved_stats = memory.get_stats_summary(
        RefinementFilter(app_instance_id=app_instance_id, queue_status=transitioned.status)
    )

    assert queue_page.meta.total_count >= 1
    assert queue_page.meta.filtered_count >= 1
    assert queue_page.meta.returned_count >= 1
    assert queue_page.items[0].proposal_id == queue_item.proposal_id
    assert stats.total_hypotheses >= 1
    assert stats.total_verifications >= 1
    assert stats.total_queue_items >= 1
    assert approved_stats.total_queue_items >= 1


def test_refinement_failed_hypothesis_page_and_failed_stats(tmp_path: Path) -> None:
    services, app_instance_id, result = _seed_refinement_run(tmp_path, failing=True)
    memory = services["memory"]

    failed_page = memory.list_failed_hypothesis_page(RefinementFilter(app_instance_id=app_instance_id, limit=5))
    failed_stats = memory.get_stats_summary(
        RefinementFilter(app_instance_id=app_instance_id, verification_outcome="failed")
    )

    assert result.verification.outcome == "failed"
    assert failed_page.meta.total_count >= 1
    assert failed_page.meta.filtered_count >= 1
    assert failed_page.meta.returned_count >= 1
    assert failed_page.items[0].app_instance_id == app_instance_id
    assert failed_stats.failed_verifications >= 1
    assert failed_stats.failed_hypotheses >= 1


def test_refinement_filter_and_stats_api_surfaces() -> None:
    queue_response = client.get(
        "/self-refinement/rollout-queue-page",
        params={"app_instance_id": "app.missing", "status": "queued", "limit": 3},
    )
    assert queue_response.status_code == 200
    queue_payload = queue_response.json()
    assert queue_payload["meta"]["total_count"] >= 0
    assert isinstance(queue_payload["items"], list)

    failed_response = client.get(
        "/self-refinement/failed-hypotheses-page",
        params={"app_instance_id": "app.missing", "limit": 3},
    )
    assert failed_response.status_code == 200
    failed_payload = failed_response.json()
    assert failed_payload["meta"]["filtered_count"] >= 0
    assert isinstance(failed_payload["items"], list)

    stats_response = client.get(
        "/self-refinement/stats",
        params={"app_instance_id": "app.missing", "verification_outcome": "failed"},
    )
    assert stats_response.status_code == 200
    stats_payload = stats_response.json()
    assert stats_payload["app_instance_id"] == "app.missing"
    assert stats_payload["failed_verifications"] >= 0
