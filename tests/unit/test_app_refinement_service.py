from __future__ import annotations

from app.models.app_blueprint import AppBlueprint
from app.models.app_refinement import SuggestedSkillRefinementClosureRequest
from app.models.skill_blueprint import SkillBlueprint
from app.models.skill_creation import AppFromSkillsResult, SkillCreationResult
from app.models.skill_runtime import SkillExecutionResult
from app.orchestration.app_refinement import AppRefinementService
from app.persistence.experience_store import ExperienceStore
from app.services.skill_control import SkillControlError


class _FakeSkillControl:
    def get_skill(self, skill_id: str):
        raise SkillControlError(skill_id)


class _FakeSkillFactory:
    def __init__(self) -> None:
        self.last_request = None

    def choose_adapter_kind_for_blueprint(self, blueprint, adapter_kind):
        return (adapter_kind or "script", False, "")

    def build_creation_request_from_blueprint(self, blueprint, adapter_kind, generation_operation, description):
        return {"skill_id": blueprint.skill_id, "adapter_kind": adapter_kind, "description": description}

    def create_skill(self, creation_request):
        return SkillCreationResult(
            skill_id=creation_request["skill_id"],
            runtime_adapter=creation_request["adapter_kind"],
            smoke_test=SkillExecutionResult(skill_id=creation_request["skill_id"], status="completed", output={}),
        )

    def build_blueprint_from_skills(self, request):
        self.last_request = request
        return (
            AppBlueprint(id=request.blueprint_id, name=request.name, goal=request.goal),
            AppFromSkillsResult(blueprint_id=request.blueprint_id, workflow_id=request.workflow_id, required_skills=list(request.skill_ids)),
        )


def test_app_refinement_service_ranks_blueprints_by_phase_h_context() -> None:
    store = ExperienceStore()
    store.add_skill_blueprint(SkillBlueprint(
        skill_id="skill.weather",
        name="Weather Helper",
        goal="show weather",
        inputs=["city"],
        outputs=["forecast"],
        steps=["query weather api"],
    ))
    store.add_skill_blueprint(SkillBlueprint(
        skill_id="skill.novel.theme",
        name="Novel Theme Refiner",
        goal="refine novel app theme and style",
        inputs=["theme"],
        outputs=["ui patch"],
        steps=["update novel theme"],
    ))

    service = AppRefinementService(
        experience_store=store,
        skill_control=_FakeSkillControl(),
        skill_factory=_FakeSkillFactory(),
    )

    ranked = service._select_blueprints(SuggestedSkillRefinementClosureRequest(
        blueprint_id="bp.novel",
        name="novel",
        target_app="novel",
        context_hints=["recent:App: novel", "modify theme"],
    ))

    assert ranked[0].skill_id == "skill.novel.theme"
    assert {item.skill_id for item in ranked} == {"skill.weather", "skill.novel.theme"}


def test_app_refinement_service_enriches_goal_with_phase_h_context() -> None:
    store = ExperienceStore()
    store.add_skill_blueprint(SkillBlueprint(
        skill_id="skill.novel.theme",
        name="Novel Theme Refiner",
        goal="refine novel app theme and style",
    ))
    factory = _FakeSkillFactory()
    service = AppRefinementService(
        experience_store=store,
        skill_control=_FakeSkillControl(),
        skill_factory=factory,
    )

    result = service.build_app_from_suggested_skills(SuggestedSkillRefinementClosureRequest(
        blueprint_id="bp.novel",
        name="novel",
        goal="refine app",
        skill_ids=["skill.novel.theme"],
        target_app="novel",
        context_hints=["recent:App: novel", "modify theme"],
    ))

    assert "target_app=novel" in factory.last_request.goal
    assert "context_hints=recent:App: novel | modify theme" in factory.last_request.goal
    assert result.blueprint.goal == factory.last_request.goal
