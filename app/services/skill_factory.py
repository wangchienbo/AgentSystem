from __future__ import annotations

from app.models.app_blueprint import AppBlueprint
from app.models.skill_creation import AppFromSkillsRequest, AppFromSkillsResult, SkillCreationRequest, SkillCreationResult
from app.models.skill_runtime import SkillExecutionRequest
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_authoring import SkillAuthoringService
from app.services.skill_control import SkillControlService
from app.services.skill_runtime import SkillRuntimeService


class SkillFactoryError(ValueError):
    pass


class SkillFactoryService:
    def __init__(
        self,
        *,
        skill_control: SkillControlService,
        skill_runtime: SkillRuntimeService,
        schema_registry: SchemaRegistryService,
        authoring: SkillAuthoringService | None = None,
    ) -> None:
        self._skill_control = skill_control
        self._skill_runtime = skill_runtime
        self._schema_registry = schema_registry
        self._authoring = authoring or SkillAuthoringService()

    def create_skill(self, request: SkillCreationRequest) -> SkillCreationResult:
        schema_refs = self._register_contracts(request)
        if request.adapter_kind == "callable":
            if not request.handler_entry:
                raise SkillFactoryError("Callable skill creation requires handler_entry")
            entry = self._authoring.build_callable_entry(
                skill_id=request.skill_id,
                name=request.name,
                handler_entry=request.handler_entry,
                description=request.description,
                input_schema_ref=schema_refs["input"],
                output_schema_ref=schema_refs["output"],
                error_schema_ref=schema_refs["error"],
                tags=request.tags,
                capability_profile=request.capability_profile,
                content=request.description or request.name,
            )
            if request.skill_id not in {item.skill_id for item in self._skill_control.list_skills()}:
                self._skill_control.register(entry)
            self._skill_runtime.register_handler(request.skill_id, self._missing_callable_stub, entry=entry)
        else:
            if not request.command:
                raise SkillFactoryError("Script skill creation requires command")
            entry = self._authoring.build_script_entry(
                skill_id=request.skill_id,
                name=request.name,
                command=request.command,
                description=request.description,
                input_schema_ref=schema_refs["input"],
                output_schema_ref=schema_refs["output"],
                error_schema_ref=schema_refs["error"],
                tags=request.tags,
                capability_profile=request.capability_profile,
                content=request.description or request.name,
            )
            if request.skill_id not in {item.skill_id for item in self._skill_control.list_skills()}:
                self._skill_control.register(entry)
            self._skill_runtime.register_handler(request.skill_id, self._script_placeholder, entry=entry)

        smoke = self._skill_runtime.execute(
            SkillExecutionRequest(
                skill_id=request.skill_id,
                app_instance_id="skill-factory",
                workflow_id="skill-smoke-test",
                step_id="smoke",
                inputs=request.smoke_test_inputs,
                config={},
            )
        )
        return SkillCreationResult(
            skill_id=request.skill_id,
            schema_refs=schema_refs,
            runtime_adapter=entry.runtime_adapter,
            smoke_test=smoke,
        )

    def build_blueprint_from_skills(self, request: AppFromSkillsRequest) -> tuple[AppBlueprint, AppFromSkillsResult]:
        missing = [skill_id for skill_id in request.skill_ids if skill_id not in {item.skill_id for item in self._skill_control.list_skills()}]
        if missing:
            raise SkillFactoryError(f"Skills not found for app assembly: {', '.join(missing)}")
        steps = []
        created_steps = []
        for index, skill_id in enumerate(request.skill_ids, start=1):
            step_id = f"skill.{index}"
            steps.append(
                {
                    "id": step_id,
                    "kind": "skill",
                    "ref": skill_id,
                    "config": {"inputs": {}},
                }
            )
            created_steps.append(step_id)
        blueprint = AppBlueprint(
            id=request.blueprint_id,
            name=request.name,
            goal=request.goal,
            roles=[],
            tasks=[],
            workflows=[
                {
                    "id": request.workflow_id,
                    "name": request.name,
                    "triggers": ["manual"],
                    "steps": steps,
                }
            ],
            required_modules=[],
            required_skills=list(request.skill_ids),
        )
        return blueprint, AppFromSkillsResult(
            blueprint_id=request.blueprint_id,
            workflow_id=request.workflow_id,
            required_skills=list(request.skill_ids),
            created_steps=created_steps,
        )

    def _register_contracts(self, request: SkillCreationRequest) -> dict[str, str]:
        refs = {
            "input": f"schema://{request.skill_id}/input",
            "output": f"schema://{request.skill_id}/output",
            "error": f"schema://{request.skill_id}/error",
        }
        self._schema_registry.register(refs["input"], request.schemas.input or {"type": "object"})
        self._schema_registry.register(refs["output"], request.schemas.output or {"type": "object"})
        self._schema_registry.register(refs["error"], request.schemas.error or {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": True})
        return refs

    @staticmethod
    def _missing_callable_stub(request: SkillExecutionRequest):
        raise SkillFactoryError(f"Callable skill stub not implemented yet: {request.skill_id}")

    @staticmethod
    def _script_placeholder(request: SkillExecutionRequest):
        raise SkillFactoryError("Script skills should execute through the script adapter entry")
