from __future__ import annotations

from copy import deepcopy

from app.models.app_blueprint import AppBlueprint
from app.models.skill_control import SkillRegistryEntry
from app.models.skill_creation import AppFromSkillsRequest, AppFromSkillsResult, SkillCreationRequest, SkillCreationResult, StepMappingDefinition
from app.models.skill_diagnostics import SkillDiagnostic, SkillDiagnosticError
from app.models.skill_runtime import SkillExecutionRequest
from app.services.generated_callable_materializer import GeneratedCallableMaterializer, GeneratedCallableMaterializerError
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_authoring import SkillAuthoringService
from app.services.skill_control import SkillControlService
from app.services.skill_runtime import SkillRuntimeService


class SkillFactoryError(ValueError):
    pass


def _diagnostic(stage: str, kind: str, message: str, *, retryable: bool = False, hint: str = "", details: dict | None = None, suggested_retry_request: dict | None = None) -> SkillDiagnosticError:
    return SkillDiagnosticError(
        SkillDiagnostic(
            stage=stage,
            kind=kind,
            message=message,
            retryable=retryable,
            hint=hint,
            details=details or {},
            suggested_retry_request=suggested_retry_request or {},
        )
    )


class SkillFactoryService:
    def __init__(
        self,
        *,
        skill_control: SkillControlService,
        skill_runtime: SkillRuntimeService,
        schema_registry: SchemaRegistryService,
        authoring: SkillAuthoringService | None = None,
        generated_assets: GeneratedSkillAssetStore | None = None,
        callable_materializer: GeneratedCallableMaterializer | None = None,
    ) -> None:
        self._skill_control = skill_control
        self._skill_runtime = skill_runtime
        self._schema_registry = schema_registry
        self._authoring = authoring or SkillAuthoringService()
        self._generated_assets = generated_assets
        self._callable_materializer = callable_materializer or GeneratedCallableMaterializer()

    def create_skill(self, request: SkillCreationRequest) -> SkillCreationResult:
        schema_refs = self._register_contracts(request)
        if request.adapter_kind == "callable":
            handler_entry = request.handler_entry
            if not handler_entry:
                if not request.generation_operation:
                    raise _diagnostic(
                        "create",
                        "invalid_request",
                        "Callable skill creation requires handler_entry or generation_operation",
                        hint="Provide handler_entry or a supported generation_operation.",
                        details={"skill_id": request.skill_id, "adapter_kind": request.adapter_kind},
                        suggested_retry_request={
                            "skill_id": request.skill_id,
                            "adapter_kind": request.adapter_kind,
                            "generation_operation": "normalize_object_keys",
                        },
                    )
                try:
                    handler_entry = self._callable_materializer.materialize_handler(
                        skill_id=request.skill_id,
                        operation=request.generation_operation,
                    )
                except GeneratedCallableMaterializerError as error:
                    raise _diagnostic(
                        "create",
                        "callable_generation_error",
                        str(error),
                        hint="Use a supported callable generation operation.",
                        details={"skill_id": request.skill_id, "generation_operation": request.generation_operation},
                        suggested_retry_request={
                            "skill_id": request.skill_id,
                            "adapter_kind": request.adapter_kind,
                            "generation_operation": "normalize_object_keys",
                        },
                    ) from error
            entry = self._authoring.build_callable_entry(
                skill_id=request.skill_id,
                name=request.name,
                handler_entry=handler_entry,
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
            try:
                handler = self._callable_materializer.load_handler(handler_entry)
            except GeneratedCallableMaterializerError as error:
                raise _diagnostic(
                    "register",
                    "adapter_error",
                    str(error),
                    hint="Check generated callable file path and handler function name.",
                    details={"skill_id": request.skill_id, "handler_entry": handler_entry},
                ) from error
            self._skill_runtime.register_handler(request.skill_id, handler, entry=entry)
        else:
            if not request.command:
                raise _diagnostic(
                    "create",
                    "invalid_request",
                    "Script skill creation requires command",
                    hint="Provide a script command list for script-backed skills.",
                    details={"skill_id": request.skill_id, "adapter_kind": request.adapter_kind},
                    suggested_retry_request={
                        "skill_id": request.skill_id,
                        "adapter_kind": request.adapter_kind,
                        "command": ["python3", "path/to/generated_skill.py"],
                    },
                )
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
        step_mappings = getattr(request, "step_mappings", {})
        known_step_ids = {f"skill.{index}" for index, _skill_id in enumerate(request.skill_ids, start=1)}
        for mapped_step_id, mappings in step_mappings.items():
            if mapped_step_id not in known_step_ids:
                raise SkillFactoryError(f"Step mappings reference unknown generated step: {mapped_step_id}")
            for mapping in mappings:
                self._apply_step_mapping({}, mapping)
        for index, skill_id in enumerate(request.skill_ids, start=1):
            step_id = f"skill.{index}"
            compiled_inputs = deepcopy(step_inputs.get(step_id, {}))
            for mapping in step_mappings.get(step_id, []):
                self._apply_step_mapping(compiled_inputs, mapping)
            steps.append(
                {
                    "id": step_id,
                    "kind": "skill",
                    "ref": skill_id,
                    "config": {"inputs": compiled_inputs},
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

    def _apply_step_mapping(self, compiled_inputs: dict, mapping: StepMappingDefinition) -> None:
        if not mapping.from_step and not mapping.from_inputs:
            raise SkillFactoryError(f"Step mapping for target '{mapping.target_field}' requires from_step or from_inputs")
        if mapping.from_step and mapping.from_inputs:
            raise SkillFactoryError(f"Step mapping for target '{mapping.target_field}' cannot set both from_step and from_inputs")
        reference: dict[str, str] = {}
        if mapping.from_step:
            reference["$from_step"] = mapping.from_step
        if mapping.from_inputs:
            reference["$from_inputs"] = mapping.from_inputs
        if mapping.field:
            reference["field"] = mapping.field
        cursor = compiled_inputs
        parts = mapping.target_field.split(".")
        for part in parts[:-1]:
            next_value = cursor.get(part)
            if next_value is None:
                next_value = {}
                cursor[part] = next_value
            if not isinstance(next_value, dict):
                raise SkillFactoryError(f"Step mapping target path '{mapping.target_field}' collides with non-object field '{part}'")
            cursor = next_value
        cursor[parts[-1]] = reference

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
                try:
                    handler = self._callable_materializer.load_handler(entry.manifest.adapter.entry if entry.manifest is not None else "")
                except GeneratedCallableMaterializerError as error:
                    raise SkillFactoryError(str(error)) from error
                self._skill_runtime.register_handler(entry.skill_id, handler, entry=entry)
            restored += 1
        return restored

    @staticmethod
    def _missing_callable_stub(request: SkillExecutionRequest):
        raise SkillFactoryError(f"Callable skill stub not implemented yet: {request.skill_id}")

    @staticmethod
    def _script_placeholder(request: SkillExecutionRequest):
        raise SkillFactoryError("Script skills should execute through the script adapter entry")
