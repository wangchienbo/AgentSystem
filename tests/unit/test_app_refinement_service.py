from __future__ import annotations

from app.models.app_refinement import SuggestedSkillRefinementClosureRequest
from app.models.skill_blueprint import SkillBlueprint
from app.orchestration.app_refinement import AppRefinementService
from app.persistence.experience_store import ExperienceStore


class _FakeSkillControl:
    def get_skill(self, skill_id: str):
        raise KeyError(skill_id)


class _FakeSkillFactory:
    pass


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
