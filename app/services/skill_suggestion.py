from __future__ import annotations

import re

from app.models.skill_blueprint import SkillBlueprint
from app.models.skill_suggestion import SkillSuggestionRequest, SkillSuggestionResult
from app.services.experience_store import ExperienceStore
from app.services.model_client import ModelClientError
from app.services.model_config_loader import ModelConfigError
from app.services.model_skill_suggester import ModelSkillSuggester


class SkillSuggestionError(ValueError):
    pass


class SkillSuggestionService:
    def __init__(
        self,
        experience_store: ExperienceStore,
        model_suggester: ModelSkillSuggester | None = None,
    ) -> None:
        self._experience_store = experience_store
        self._model_suggester = model_suggester

    def suggest(self, request: SkillSuggestionRequest) -> SkillSuggestionResult:
        experience = self._get_experience(request.experience_id)
        slug = self._slugify(experience.title)
        fallback_skill_id = f"skill.suggested.{slug}"
        suggestion = self._build_fallback_suggestion(experience, fallback_skill_id)

        if self._model_suggester and self._model_suggester.is_available():
            try:
                suggestion = self._model_suggester.suggest(experience, fallback_skill_id=fallback_skill_id)
            except (ModelConfigError, ModelClientError, KeyError, TypeError, ValueError):
                suggestion = self._build_fallback_suggestion(experience, fallback_skill_id)

        persisted = False
        if request.persist:
            self._experience_store.add_skill_blueprint(suggestion)
            persisted = True
        return SkillSuggestionResult(
            experience_id=experience.experience_id,
            suggestion=suggestion,
            persisted=persisted,
        )

    def _get_experience(self, experience_id: str):
        for experience in self._experience_store.list_experiences():
            if experience.experience_id == experience_id:
                return experience
        raise SkillSuggestionError(f"Experience not found: {experience_id}")

    def _slugify(self, text: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", ".", text.strip().lower())
        normalized = re.sub(r"\.+", ".", normalized).strip(".")
        return normalized or "runtime.experience"

    def _build_fallback_suggestion(self, experience, fallback_skill_id: str) -> SkillBlueprint:
        return SkillBlueprint(
            skill_id=fallback_skill_id,
            name=f"Suggested Skill for {experience.title}",
            goal=f"将经验 {experience.experience_id} 中的重复实践抽象成可复用 skill",
            inputs=["context", "runtime_event", "app_data_record"],
            outputs=["action_plan", "structured_result"],
            steps=self._build_steps(experience.summary),
            related_experience_ids=[experience.experience_id],
        )

    def _build_steps(self, summary: str) -> list[str]:
        return [
            "inspect runtime context and recent app data",
            "match the current case against summarized runtime experience",
            f"apply rule distilled from experience: {summary}",
            "return a structured action plan for the app workflow",
        ]
