from __future__ import annotations

from typing import Any

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
            previous_step_ids: list[str] = []
            for step in workflow.steps:
                if step.kind != "skill":
                    previous_step_ids.append(step.id)
                    continue
                runtime_step_skills.append(step.ref)
                if step.ref not in declared_skills:
                    errors.append(f"Workflow step {workflow.id}:{step.id} references undeclared skill: {step.ref}")
                    previous_step_ids.append(step.id)
                    continue
                try:
                    entry = self._skill_validation.get_runtime_skill_entry(step.ref)
                    errors.extend(self._validate_skill_step_contracts(workflow.id, step.id, step.config.get("inputs", {}), previous_step_ids, entry.manifest.contract.input_schema_ref if entry.manifest is not None else ""))
                except SkillValidationError as error:
                    errors.append(str(error))
                previous_step_ids.append(step.id)

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

    def _validate_skill_step_contracts(
        self,
        workflow_id: str,
        step_id: str,
        inputs: dict[str, Any],
        previous_step_ids: list[str],
        input_schema_ref: str,
    ) -> list[str]:
        errors: list[str] = []
        if not input_schema_ref:
            errors.extend(self._validate_references(workflow_id, step_id, inputs, previous_step_ids, None))
            return errors
        schema_registry = getattr(self._skill_validation._manifest_validator, "_schema_registry", None)
        schema = None if schema_registry is None else schema_registry.resolve(input_schema_ref)
        errors.extend(self._validate_references(workflow_id, step_id, inputs, previous_step_ids, schema))
        if isinstance(schema, dict) and schema.get("type") == "object":
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            if isinstance(inputs, dict):
                for key in required:
                    if key not in inputs:
                        errors.append(f"Workflow step {workflow_id}:{step_id} missing required input field: {key}")
                for key in inputs:
                    if key not in properties and schema.get("additionalProperties", True) is False:
                        errors.append(f"Workflow step {workflow_id}:{step_id} uses undeclared input field: {key}")
        return errors

    def _validate_references(
        self,
        workflow_id: str,
        step_id: str,
        value: Any,
        previous_step_ids: list[str],
        schema: dict[str, Any] | None,
        path: str = "",
    ) -> list[str]:
        errors: list[str] = []
        if isinstance(value, dict) and "$from_step" in value:
            source_step = str(value["$from_step"])
            if source_step not in previous_step_ids:
                errors.append(f"Workflow step {workflow_id}:{step_id} references unknown or future step: {source_step}")
            if schema is not None and path:
                properties = schema.get("properties", {}) if schema.get("type") == "object" else {}
                top_field = path.split(".")[0]
                if top_field not in properties and schema.get("additionalProperties", True) is False:
                    errors.append(f"Workflow step {workflow_id}:{step_id} maps into undeclared input field: {top_field}")
            return errors
        if isinstance(value, dict) and "$from_inputs" in value:
            if schema is not None and path:
                properties = schema.get("properties", {}) if schema.get("type") == "object" else {}
                top_field = path.split(".")[0]
                if top_field not in properties and schema.get("additionalProperties", True) is False:
                    errors.append(f"Workflow step {workflow_id}:{step_id} maps external inputs into undeclared field: {top_field}")
            return errors
        if isinstance(value, dict):
            for key, item in value.items():
                next_path = key if not path else f"{path}.{key}"
                errors.extend(self._validate_references(workflow_id, step_id, item, previous_step_ids, schema, next_path))
        elif isinstance(value, list):
            for item in value:
                errors.extend(self._validate_references(workflow_id, step_id, item, previous_step_ids, schema, path))
        return errors
