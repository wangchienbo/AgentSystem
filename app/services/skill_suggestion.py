from __future__ import annotations

import re

from app.models.skill_blueprint import SkillBlueprint
from app.models.skill_suggestion import SkillSuggestionRequest, SkillSuggestionResult
from app.services.experience_store import ExperienceStore
from app.services.model_client import ModelClientError
from app.services.model_config_loader import ModelConfigError
from app.services.model_skill_suggester import ModelSkillSuggester
from app.services.skill_risk_policy import SkillRiskPolicyService


class SkillSuggestionError(ValueError):
    pass


class SkillSuggestionService:
    def __init__(
        self,
        experience_store: ExperienceStore,
        model_suggester: ModelSkillSuggester | None = None,
        risk_policy: SkillRiskPolicyService | None = None,
    ) -> None:
        self._experience_store = experience_store
        self._model_suggester = model_suggester
        self._risk_policy = risk_policy

    def suggest(self, request: SkillSuggestionRequest) -> SkillSuggestionResult:
        experience = self._get_experience(request.experience_id)
        governance_context = self._build_governance_context()
        slug = self._slugify(experience.title)
        fallback_skill_id = f"skill.suggested.{slug}"
        suggestion = self._build_fallback_suggestion(experience, fallback_skill_id, governance_context)

        if self._model_suggester and self._model_suggester.is_available():
            try:
                suggestion = self._model_suggester.suggest(experience, fallback_skill_id=fallback_skill_id)
            except (ModelConfigError, ModelClientError, KeyError, TypeError, ValueError):
                suggestion = self._build_fallback_suggestion(experience, fallback_skill_id, governance_context)

        persisted = False
        if request.persist:
            self._experience_store.add_skill_blueprint(suggestion)
            persisted = True
        return SkillSuggestionResult(
            experience_id=experience.experience_id,
            suggestion=suggestion,
            persisted=persisted,
            governance_context=governance_context,
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

    def _build_fallback_suggestion(self, experience, fallback_skill_id: str, governance_context: dict) -> SkillBlueprint:
        return SkillBlueprint(
            skill_id=fallback_skill_id,
            name=f"Suggested Skill for {experience.title}",
            goal=f"将经验 {experience.experience_id} 中的重复实践抽象成可复用 skill",
            inputs=["context", "runtime_event", "app_data_record"],
            outputs=["action_plan", "structured_result"],
            steps=self._build_steps(experience.summary, governance_context),
            related_experience_ids=[experience.experience_id],
        )

    def _build_governance_context(self) -> dict:
        if self._risk_policy is None:
            return {"risk_governance_enabled": False}
        stats = self._risk_policy.get_stats_summary()
        return {
            "risk_governance_enabled": True,
            "blocked_events": stats.blocked_events,
            "active_overrides": stats.active_overrides,
            "recent_policy_pressure": stats.blocked_events > 0,
        }

    def _build_steps(self, summary: str, governance_context: dict) -> list[str]:
        steps = [
            "inspect runtime context and recent app data",
            "match the current case against summarized runtime experience",
            f"apply rule distilled from experience: {summary}",
            "return a structured action plan for the app workflow",
        ]
        if governance_context.get("recent_policy_pressure"):
            steps.insert(2, "prefer deterministic local execution and avoid shell/network side effects unless explicitly required")
        return steps
