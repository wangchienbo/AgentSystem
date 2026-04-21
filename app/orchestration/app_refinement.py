from __future__ import annotations

import re

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
            chosen_adapter, _adjusted, _reason = self._skill_factory.choose_adapter_kind_for_blueprint(
                blueprint,
                request.adapter_kind,
            )
            generation_operation = "normalize_object_keys" if chosen_adapter == "callable" else ""
            creation_request = self._skill_factory.build_creation_request_from_blueprint(
                blueprint,
                adapter_kind=chosen_adapter,
                generation_operation=generation_operation,
                description=blueprint.goal,
            )
            created_skills.append(self._skill_factory.create_skill(creation_request))
            reusable_skill_ids.append(blueprint.skill_id)

        enriched_goal = self._build_contextual_goal(request)
        blueprint, app_result = self._skill_factory.build_blueprint_from_skills(
            request.model_copy(update={"skill_ids": reusable_skill_ids, "goal": enriched_goal})
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
            return self._rank_blueprints_by_context(
                self._experience_store.suggest_skills_for_experience(request.experience_id),
                request,
            )
        return self._rank_blueprints_by_context(
            self._experience_store.list_skill_blueprints(),
            request,
        )

    def _rank_blueprints_by_context(
        self,
        blueprints: list[SkillBlueprint],
        request: SuggestedSkillRefinementRequest,
    ) -> list[SkillBlueprint]:
        target_app = str(getattr(request, "target_app", "") or "")
        context_hints = list(getattr(request, "context_hints", []) or [])
        context_text = " ".join([target_app, *context_hints]).strip().lower()
        if not context_text:
            return blueprints

        tokens = [token for token in re.split(r"[^a-z0-9_\-.]+", context_text) if len(token) >= 2]
        if not tokens:
            return blueprints

        def _score(blueprint: SkillBlueprint) -> tuple[int, str]:
            haystack_parts = [
                blueprint.skill_id,
                blueprint.name,
                blueprint.goal,
                *blueprint.inputs,
                *blueprint.outputs,
                *blueprint.steps,
                *blueprint.related_experience_ids,
            ]
            haystack = " ".join(haystack_parts).lower()
            score = 0
            for token in tokens:
                if token == target_app.lower() and token and token in haystack:
                    score += 4
                elif token in haystack:
                    score += 1
            return (-score, blueprint.skill_id)

        return sorted(blueprints, key=_score)

    def _build_contextual_goal(self, request: SuggestedSkillRefinementRequest) -> str:
        goal = (request.goal or "refine app from suggested skills").strip()
        target_app = str(getattr(request, "target_app", "") or "").strip()
        context_hints = [str(item).strip() for item in list(getattr(request, "context_hints", []) or []) if str(item).strip()]

        extra_parts: list[str] = []
        if target_app:
            extra_parts.append(f"target_app={target_app}")
        if context_hints:
            extra_parts.append("context_hints=" + " | ".join(context_hints[:3]))
        if not extra_parts:
            return goal
        return f"{goal} [{'; '.join(extra_parts)}]"
