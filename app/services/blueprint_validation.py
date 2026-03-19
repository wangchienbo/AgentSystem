from __future__ import annotations

from app.models.app_blueprint import AppBlueprint
from app.services.skill_validation import SkillValidationError, SkillValidationService


class BlueprintValidationError(ValueError):
    pass


class BlueprintValidationService:
    def __init__(self, skill_validation: SkillValidationService) -> None:
        self._skill_validation = skill_validation

    def validate(self, blueprint: AppBlueprint) -> dict[str, object]:
        missing: list[str] = []
        errors: list[str] = []

        if not blueprint.roles:
            missing.append("roles")
        if not blueprint.workflows:
            missing.append("workflows")

        declared_skills = set(blueprint.required_skills)
        runtime_step_skills: list[str] = []

        for workflow in blueprint.workflows:
            for step in workflow.steps:
                if step.kind != "skill":
                    continue
                runtime_step_skills.append(step.ref)
                if step.ref not in declared_skills:
                    errors.append(f"Workflow step {workflow.id}:{step.id} references undeclared skill: {step.ref}")
                    continue
                try:
                    self._skill_validation.validate_runtime_skill(step.ref)
                except SkillValidationError as error:
                    errors.append(str(error))

        for skill_id in blueprint.required_skills:
            try:
                self._skill_validation.validate_skill_exists(skill_id)
            except SkillValidationError as error:
                errors.append(str(error))

        return {
            "ok": len(missing) == 0 and len(errors) == 0,
            "missing": missing,
            "errors": errors,
            "blueprint_id": blueprint.id,
            "runtime_step_skills": runtime_step_skills,
        }

    def require_valid(self, blueprint: AppBlueprint) -> dict[str, object]:
        result = self.validate(blueprint)
        if not result["ok"]:
            problems = []
            if result["missing"]:
                problems.append(f"missing fields: {', '.join(result['missing'])}")
            if result["errors"]:
                problems.extend(result["errors"])
            raise BlueprintValidationError("; ".join(problems))
        return result
