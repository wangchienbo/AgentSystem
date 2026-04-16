from __future__ import annotations

from app.models.demonstration import DemonstrationRecord
from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint


class DemonstrationExtractor:
    def extract(self, record: DemonstrationRecord) -> tuple[ExperienceRecord, SkillBlueprint]:
        normalized_steps = [step.strip() for step in record.steps if step.strip()]
        experience = ExperienceRecord(
            experience_id=f"exp.{record.demonstration_id}",
            title=f"Experience from {record.title}",
            summary=f"Demonstrated goal: {record.goal}. Key steps: {'; '.join(normalized_steps[:3])}",
            source="demonstration",
            tags=["demonstration", "learned"],
        )
        skill = SkillBlueprint(
            skill_id=f"skill.{record.demonstration_id}",
            name=record.title,
            goal=record.goal,
            inputs=record.observed_inputs,
            outputs=record.observed_outputs,
            steps=normalized_steps,
            related_experience_ids=[experience.experience_id],
        )
        return experience, skill
