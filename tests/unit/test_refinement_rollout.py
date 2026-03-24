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


def test_refinement_rollout_queue_lifecycle(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "refinement-rollout-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "refinement-rollout-ns"), store=store)
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
        verification_executor=stub_verification_executor,
    )
    rollout = RefinementRolloutService(memory=memory, proposal_review=proposal_service)

    registry.register_blueprint(
        AppBlueprint(
            id="bp.refinement.rollout",
            name="Refinement Rollout App",
            goal="exercise rollout queue lifecycle",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.rollout", "name": "rollout", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install = installer.install_app("bp.refinement.rollout", user_id="rollout-user")
    app_instance_id = install.app_instance_id

    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="open_loops",
        key="rollout-followup",
        value={"needed": True},
        tags=["rollout"],
    )
    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="rollout-log",
        value={"status": "needs governance"},
        tags=["rollout"],
    )
    review = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))
    proposals = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id)
    )
    proposal_service.register_proposals(proposals)
    result = loop.run(RefinementLoopRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id))
    queue_item = result.queue_item
    assert queue_item is not None

    if queue_item.status == "queued":
        approved = rollout.transition(queue_item.queue_id, "approve", reviewer="tester", note="approved for manual apply")
        assert approved.status == "approved"
        rejected = rollout.transition(approved.queue_id, "reject", reviewer="tester", note="rejected after review")
        assert rejected.status == "rejected"
    else:
        rolled_back = rollout.transition(queue_item.queue_id, "rollback", reviewer="tester", note="rolled back after apply")
        assert rolled_back.status == "rolled_back"


def test_refinement_rollout_queue_api_surfaces() -> None:
    queue_response = client.get("/self-refinement/rollout-queue")
    assert queue_response.status_code == 200
    assert isinstance(queue_response.json(), list)
