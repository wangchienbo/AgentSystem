from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.experience import ExperienceRecord
from app.models.patch_proposal import PatchProposal, SelfRefinementRequest
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


class StubModelSelfRefiner:
    def __init__(self, available: bool = True, should_fail: bool = False) -> None:
        self._available = available
        self._should_fail = should_fail

    def is_available(self) -> bool:
        return self._available

    def propose(self, app_instance_id, blueprint, experience):
        if self._should_fail:
            raise ValueError("model failed")
        return [
            PatchProposal(
                proposal_id=f"proposal.model.{app_instance_id}.1",
                app_instance_id=app_instance_id,
                target_type="workflow",
                title="Model-generated workflow refinement",
                summary="Use model synthesis to add an explicit reflection checkpoint.",
                evidence=[experience.summary],
                expected_benefit="Improve adaptation quality before action execution.",
                risk_level="medium",
                auto_apply_allowed=False,
                validation_checklist=["validate generated workflow patch"],
                rollback_target="restore previous workflow",
                patch={"workflow_id": blueprint.workflows[0].id, "append_step": {"kind": "module", "ref": "state.get"}},
            )
        ]


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



def test_self_refinement_uses_model_when_available() -> None:
    store = RuntimeStateStore(base_dir="data/test-self-refinement-model")
    data_store = AppDataStore(base_dir="data/test-self-refinement-model-ns", store=store)
    experience_store = ExperienceStore()
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    installer = AppInstallerService(registry=registry, lifecycle=lifecycle, runtime_host=runtime, data_store=data_store)
    refinement_service = SelfRefinementService(
        experience_store=experience_store,
        registry=registry,
        lifecycle=lifecycle,
        model_self_refiner=StubModelSelfRefiner(),
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.self.refinement.model",
            name="Self Refinement Model App",
            goal="generate model refinement proposals",
            roles=[],
            tasks=[],
            workflows=[{"id": "wf.model", "name": "model", "triggers": ["manual"], "steps": []}],
            required_modules=["state.get"],
            required_skills=[],
            runtime_policy={"execution_mode": "service", "idle_strategy": "keep_alive"},
        )
    )
    install_result = installer.install_app("bp.self.refinement.model", user_id="model.user")
    experience_store.add_experience(
        ExperienceRecord(
            experience_id="exp.model.self.1",
            title="Model self refinement experience",
            summary="系统需要在执行前增加显式反思检查点。",
            source="runtime",
        )
    )

    result = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=install_result.app_instance_id, experience_id="exp.model.self.1")
    )

    assert result.proposals[0].title == "Model-generated workflow refinement"



def test_self_refinement_falls_back_when_model_fails() -> None:
    store = RuntimeStateStore(base_dir="data/test-self-refinement-fallback")
    data_store = AppDataStore(base_dir="data/test-self-refinement-fallback-ns", store=store)
    experience_store = ExperienceStore()
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    registry = AppRegistryService(store=store)
    installer = AppInstallerService(registry=registry, lifecycle=lifecycle, runtime_host=runtime, data_store=data_store)
    refinement_service = SelfRefinementService(
        experience_store=experience_store,
        registry=registry,
        lifecycle=lifecycle,
        model_self_refiner=StubModelSelfRefiner(should_fail=True),
    )

    blueprint = AppBlueprint(
        id="bp.self.refinement.fallback",
        name="Self Refinement Fallback App",
        goal="generate fallback proposals",
        roles=[],
        tasks=[],
        workflows=[{"id": "wf.fallback", "name": "fallback", "triggers": ["manual"], "steps": []}],
        required_modules=["state.get"],
        required_skills=[],
        runtime_policy={"execution_mode": "service", "idle_strategy": "suspend"},
    )
    registry.register_blueprint(blueprint)
    install_result = installer.install_app("bp.self.refinement.fallback", user_id="fallback.user")
    experience_store.add_experience(
        ExperienceRecord(
            experience_id="exp.model.self.2",
            title="Fallback self refinement experience",
            summary="即使模型失败也要保留规则化 proposal。",
            source="runtime",
        )
    )

    result = refinement_service.propose(
        SelfRefinementRequest(app_instance_id=install_result.app_instance_id, experience_id="exp.model.self.2")
    )

    assert any(item.target_type == "workflow" for item in result.proposals)
    assert any(item.target_type == "runtime_policy" for item in result.proposals)



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
