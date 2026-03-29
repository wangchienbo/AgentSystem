from __future__ import annotations

from app.models.app_refinement import SuggestedSkillRefinementRequest, SuggestedSkillRefinementResult
from app.models.skill_blueprint import SkillBlueprint
from app.services.experience_store import ExperienceStore
from app.services.skill_control import SkillControlService, SkillControlError
from app.services.skill_factory import SkillFactoryService, SkillFactoryError


class AppRefinementError(ValueError):
    pass


class AppRefinementService:
    def __init__(
        self,
        *,
        experience_store: ExperienceStore,
        skill_control: SkillControlService,
        skill_factory: SkillFactoryService,
    ) -> None:
        self._experience_store = experience_store
        self._skill_control = skill_control
        self._skill_factory = skill_factory

    def build_app_from_suggested_skills(self, request: SuggestedSkillRefinementRequest) -> SuggestedSkillRefinementResult:
        selected = self._select_blueprints(request)
        if not selected:
            raise AppRefinementError("No suggested skill blueprints found for app refinement")

        created_skills = []
        reusable_skill_ids: list[str] = []
        for blueprint in selected:
            try:
                self._skill_control.get_skill(blueprint.skill_id)
                reusable_skill_ids.append(blueprint.skill_id)
                continue
            except SkillControlError:
                pass
            creation_request = self._skill_factory.build_creation_request_from_blueprint(
                blueprint,
                adapter_kind="callable",
                generation_operation="normalize_object_keys",
                description=blueprint.goal,
            )
            created_skills.append(self._skill_factory.create_skill(creation_request))
            reusable_skill_ids.append(blueprint.skill_id)

        blueprint, app_result = self._skill_factory.build_blueprint_from_skills(
            request.model_copy(update={"skill_ids": reusable_skill_ids})
        )
        return SuggestedSkillRefinementResult(
            blueprint=blueprint,
            app_result=app_result,
            created_skills=created_skills,
            reused_skill_ids=reusable_skill_ids,
            selected_blueprints=selected,
        )

    def _select_blueprints(self, request: SuggestedSkillRefinementRequest) -> list[SkillBlueprint]:
        if request.skill_ids:
            found = []
            missing = []
            for skill_id in request.skill_ids:
                try:
                    found.append(self._experience_store.get_skill_blueprint(skill_id))
                except KeyError:
                    missing.append(skill_id)
            if missing:
                raise AppRefinementError(f"Suggested skill blueprints not found: {', '.join(missing)}")
            return found
        if request.experience_id:
            return self._experience_store.suggest_skills_for_experience(request.experience_id)
        return self._experience_store.list_skill_blueprints()
