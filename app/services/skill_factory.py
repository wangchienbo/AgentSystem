from __future__ import annotations

from copy import deepcopy

from app.models.app_blueprint import AppBlueprint
from app.models.skill_control import SkillRegistryEntry
from app.models.skill_creation import AppFromSkillsRequest, AppFromSkillsResult, SkillCreationRequest, SkillCreationResult
from app.models.skill_runtime import SkillExecutionRequest
from app.services.generated_skill_assets import GeneratedSkillAssetStore
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
        generated_assets: GeneratedSkillAssetStore | None = None,
    ) -> None:
        self._skill_control = skill_control
        self._skill_runtime = skill_runtime
        self._schema_registry = schema_registry
        self._authoring = authoring or SkillAuthoringService()
        self._generated_assets = generated_assets

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
        if self._generated_assets is not None:
            self._generated_assets.persist_generated_skill(request=request, schema_refs=schema_refs, entry=entry)
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
        step_inputs = getattr(request, "step_inputs", {})
        for index, skill_id in enumerate(request.skill_ids, start=1):
            step_id = f"skill.{index}"
            steps.append(
                {
                    "id": step_id,
                    "kind": "skill",
                    "ref": skill_id,
                    "config": {"inputs": step_inputs.get(step_id, {})},
                }
            )
            created_steps.append(step_id)
        blueprint = AppBlueprint(
            id=request.blueprint_id,
            name=request.name,
            goal=request.goal,
            roles=[{"id": "generated.agent", "name": "Generated Agent", "type": "agent"}],
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
        input_schema = deepcopy(request.schemas.input or {"type": "object"})
        if input_schema.get("type") == "object":
            properties = input_schema.setdefault("properties", {})
            properties.setdefault("working_set", {"type": "object"})
        self._schema_registry.register(refs["input"], input_schema)
        self._schema_registry.register(refs["output"], request.schemas.output or {"type": "object"})
        self._schema_registry.register(refs["error"], request.schemas.error or {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": True})
        return refs

    def reload_generated_skills(self) -> int:
        if self._generated_assets is None:
            return 0
        restored = 0
        for asset in self._generated_assets.list_generated_assets():
            entry = SkillRegistryEntry.model_validate(asset["entry"])
            contract = entry.manifest.contract if entry.manifest is not None else None
            schemas = asset.get("schemas", {})
            if contract is not None:
                if contract.input_schema_ref and schemas.get("input"):
                    self._schema_registry.register(contract.input_schema_ref, schemas["input"])
                if contract.output_schema_ref and schemas.get("output"):
                    self._schema_registry.register(contract.output_schema_ref, schemas["output"])
                if contract.error_schema_ref and schemas.get("error"):
                    self._schema_registry.register(contract.error_schema_ref, schemas["error"])
            try:
                self._skill_control.get_skill(entry.skill_id)
            except Exception:
                self._skill_control.register(entry)
            if entry.runtime_adapter == "script":
                self._skill_runtime.register_handler(entry.skill_id, self._script_placeholder, entry=entry)
            else:
                self._skill_runtime.register_handler(entry.skill_id, self._missing_callable_stub, entry=entry)
            restored += 1
        return restored

    @staticmethod
    def _missing_callable_stub(request: SkillExecutionRequest):
        raise SkillFactoryError(f"Callable skill stub not implemented yet: {request.skill_id}")

    @staticmethod
    def _script_placeholder(request: SkillExecutionRequest):
        raise SkillFactoryError("Script skills should execute through the script adapter entry")
