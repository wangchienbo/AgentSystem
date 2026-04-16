from __future__ import annotations

from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint


class ExperienceStore:
    def __init__(self) -> None:
        self._experiences: dict[str, ExperienceRecord] = {}
        self._skills: dict[str, SkillBlueprint] = {}

    def add_experience(self, record: ExperienceRecord) -> ExperienceRecord:
        self._experiences[record.experience_id] = record
        return record

    def list_experiences(self) -> list[ExperienceRecord]:
        return list(self._experiences.values())

    def add_skill_blueprint(self, blueprint: SkillBlueprint) -> SkillBlueprint:
        self._skills[blueprint.skill_id] = blueprint
        return blueprint

    def list_skill_blueprints(self) -> list[SkillBlueprint]:
        return list(self._skills.values())

    def get_skill_blueprint(self, skill_id: str) -> SkillBlueprint:
        try:
            return self._skills[skill_id]
        except KeyError as error:
            raise KeyError(f"Skill blueprint not found: {skill_id}") from error

    def suggest_skills_for_experience(self, experience_id: str) -> list[SkillBlueprint]:
        return [
            blueprint
            for blueprint in self._skills.values()
            if experience_id in blueprint.related_experience_ids
        ]
