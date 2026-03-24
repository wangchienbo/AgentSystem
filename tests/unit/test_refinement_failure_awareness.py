from pathlib import Path

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


class StubCompletedProcess:
    def __init__(self, returncode: int = 1, stdout: str = "failed", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def failing_verification_executor(_runner_path: str) -> StubCompletedProcess:
    return StubCompletedProcess(returncode=1, stdout="grouped regression failed")


def passing_verification_executor(_runner_path: str) -> StubCompletedProcess:
    return StubCompletedProcess(returncode=0, stdout="grouped regression passed")


def test_refinement_loop_uses_failed_archive_to_raise_repeat_risk(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "refinement-failure-aware-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "refinement-failure-aware-ns"), store=store)
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
            id="bp.refinement.failure-aware",
            name="Refinement Failure Aware App",
            goal="avoid repeating disproven hypotheses",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.failure-aware", "name": "failure-aware", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install = installer.install_app("bp.refinement.failure-aware", user_id="failure-aware-user")
    app_instance_id = install.app_instance_id

    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="open_loops",
        key="failure-aware-followup",
        value={"needed": True},
        tags=["failure-aware"],
    )
    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="failure-aware-log",
        value={"status": "same contradiction persists"},
        tags=["failure-aware"],
    )
    review = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))
    proposals = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id)
    )
    proposal_service.register_proposals(proposals)

    first_loop = RefinementLoopService(
        proposal_review=proposal_service,
        priority_analysis=analyzer,
        memory=memory,
        verification_executor=failing_verification_executor,
    )
    first = first_loop.run(RefinementLoopRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id))
    assert first.verification.outcome == "failed"
    assert memory.list_failed_hypotheses(app_instance_id=app_instance_id)

    second_loop = RefinementLoopService(
        proposal_review=proposal_service,
        priority_analysis=analyzer,
        memory=memory,
        verification_executor=passing_verification_executor,
    )
    second = second_loop.run(RefinementLoopRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id))
    assert second.hypothesis.repeat_risk in {"medium", "high"}
    assert second.hypothesis.related_failed_hypothesis_ids
    assert second.verification.failure_aware is True
    assert second.verification.gating_reason
    assert second.rollout.status == "hold"
