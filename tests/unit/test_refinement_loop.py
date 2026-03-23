from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.experience import ExperienceRecord
from app.models.patch_proposal import SelfRefinementRequest
from app.models.practice_review import PracticeReviewRequest
from app.models.priority_analysis import PriorityAnalysisRequest
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
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def stub_verification_executor(_runner_path: str) -> StubCompletedProcess:
    return StubCompletedProcess(returncode=0, stdout="grouped regression passed")


class StubProposalReviewService(ProposalReviewService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.applied: list[str] = []

    def review(self, request):
        result = super().review(request)
        if request.action == "apply":
            self.applied.append(request.proposal_id)
        return result


def test_refinement_loop_turns_priority_into_hypothesis_and_rollout(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "refinement-loop-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "refinement-loop-ns"), store=store)
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
    proposal_service = StubProposalReviewService(lifecycle=lifecycle, store=store, context_store=context_store)
    analyzer = PriorityAnalysisService(proposal_review=proposal_service, context_store=context_store)
    loop = RefinementLoopService(
        proposal_review=proposal_service,
        priority_analysis=analyzer,
        memory=RefinementMemoryStore(),
        regression_runner="/root/project/AgentSystem/scripts/run_test_groups.sh",
        verification_executor=stub_verification_executor,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.refinement.loop",
            name="Refinement Loop App",
            goal="close the loop from contradiction to rollout",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.loop", "name": "loop", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
        )
    )
    install = installer.install_app("bp.refinement.loop", user_id="loop-user")
    app_instance_id = install.app_instance_id

    context_store.append_entry(
        app_instance_id=app_instance_id,
        section="open_loops",
        key="loop-followup",
        value={"needed": True},
        tags=["followup"],
    )
    event_bus.publish("runtime.reviewed", source="test", app_instance_id=app_instance_id)
    data_store.put_record(
        namespace_id=f"{app_instance_id}:app_data",
        key="loop-log",
        value={"status": "needs optimization"},
        tags=["review"],
    )
    review = review_service.review(PracticeReviewRequest(app_instance_id=app_instance_id))
    proposals = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id)
    )
    proposal_service.register_proposals(proposals)

    result = loop.run(RefinementLoopRequest(app_instance_id=app_instance_id, experience_id=review.experience.experience_id))

    assert "主要矛盾" in result.primary_contradiction
    assert result.hypothesis.proposal_id == result.hypothesis.proposal_id
    assert result.hypothesis.experience_id == review.experience.experience_id
    assert result.experiment.status == "completed"
    assert result.experiment.validation_mode in {"grouped_regression", "checklist"}
    assert result.verification.outcome in {"passed", "inconclusive", "failed"}
    assert result.verification.execution_reference.startswith(("grouped_regression:", "checklist:"))
    assert result.rollout.status in {"promote", "hold"}
    if result.rollout.status == "promote":
        assert proposal_service.applied
    assert loop.memory.list_hypotheses(app_instance_id)
    assert loop.memory.list_decisions(result.hypothesis.hypothesis_id)


def test_refinement_loop_query_api_flow() -> None:
    hypotheses_response = client.get("/self-refinement/hypotheses")
    assert hypotheses_response.status_code == 200
    assert isinstance(hypotheses_response.json(), list)

    experiments_response = client.get("/self-refinement/experiments")
    assert experiments_response.status_code == 200
    assert isinstance(experiments_response.json(), list)

    verifications_response = client.get("/self-refinement/verifications")
    assert verifications_response.status_code == 200
    assert isinstance(verifications_response.json(), list)

    decisions_response = client.get("/self-refinement/decisions")
    assert decisions_response.status_code == 200
    assert isinstance(decisions_response.json(), list)
