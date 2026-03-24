from __future__ import annotations

from copy import deepcopy

from app.models.app_blueprint import AppBlueprint
from app.models.skill_blueprint import SkillBlueprint
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry
from app.models.skill_creation import AppFromSkillsRequest, AppFromSkillsResult, SkillCreationRequest, SkillCreationResult, StepMappingDefinition, SuggestedStepMapping
from app.models.skill_diagnostics import SkillDiagnostic, SkillDiagnosticError
from app.models.skill_runtime import SkillExecutionRequest
from app.services.generated_callable_materializer import GeneratedCallableMaterializer, GeneratedCallableMaterializerError
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_authoring import SkillAuthoringService
from app.services.skill_risk_policy import SkillRiskPolicyService
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


BLOCKED_GENERATED_APP_RISK_LEVELS = {"R2_shell", "R3_filesystem_write", "R4_networked", "R5_high_risk"}


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
        risk_policy: SkillRiskPolicyService | None = None,
    ) -> None:
        self._skill_control = skill_control
        self._skill_runtime = skill_runtime
        self._schema_registry = schema_registry
        self._authoring = authoring or SkillAuthoringService()
        self._generated_assets = generated_assets
        self._callable_materializer = callable_materializer or GeneratedCallableMaterializer()
        self._risk_policy = risk_policy or SkillRiskPolicyService()

    def build_creation_defaults_from_blueprint(self, blueprint: SkillBlueprint) -> dict:
        safety_profile = blueprint.safety_profile or {}
        capability_profile = SkillCapabilityProfile(
            intelligence_level="L0_deterministic" if safety_profile.get("prefer_deterministic", True) else "L1_assisted",
            network_requirement="N0_none" if safety_profile.get("allow_network") is False else "N1_optional",
            runtime_criticality="C2_required_runtime",
            execution_locality="local" if safety_profile.get("prefer_local_only") else "hybrid",
            invocation_default="automatic",
            risk_level=safety_profile.get("preferred_risk_level", "R0_safe_read"),
        )
        manifest_risk = {
            "risk_level": safety_profile.get("preferred_risk_level", "R0_safe_read"),
            "allow_network": bool(safety_profile.get("allow_network", False)),
            "allow_shell": bool(safety_profile.get("allow_shell", False)),
            "allow_filesystem_write": bool(safety_profile.get("allow_filesystem_write", False)),
        }
        return {
            "capability_profile": capability_profile,
            "manifest_risk": manifest_risk,
            "safety_profile": safety_profile,
        }

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
        for skill_id in request.skill_ids:
            entry = self._skill_control.get_skill(skill_id)
            self._assert_generated_app_safe(entry)
        steps = []
        created_steps = []
        suggested_mappings: list[SuggestedStepMapping] = []
        unresolved_inputs: dict[str, list[str]] = {}
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
            explicit_target_fields = {mapping.target_field for mapping in step_mappings.get(step_id, [])}
            prior_skill_id = request.skill_ids[index - 2] if index > 1 else ""
            if prior_skill_id:
                suggestions, unresolved = self._suggest_step_mappings(
                    step_id=step_id,
                    source_step_id=f"skill.{index - 1}",
                    source_skill_id=prior_skill_id,
                    target_skill_id=skill_id,
                    existing_inputs=compiled_inputs,
                    explicit_target_fields=explicit_target_fields,
                )
                self._apply_suggested_mappings(compiled_inputs, suggestions)
                suggested_mappings.extend(suggestions)
                if unresolved:
                    unresolved_inputs[step_id] = unresolved
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
            suggested_mappings=suggested_mappings,
            unresolved_inputs=unresolved_inputs,
        )

    def _suggest_step_mappings(
        self,
        *,
        step_id: str,
        source_step_id: str,
        source_skill_id: str,
        target_skill_id: str,
        existing_inputs: dict,
        explicit_target_fields: set[str],
    ) -> tuple[list[SuggestedStepMapping], list[str]]:
        source_entry = self._skill_control.get_skill(source_skill_id)
        target_entry = self._skill_control.get_skill(target_skill_id)
        source_contract = source_entry.manifest.contract if source_entry.manifest is not None else None
        target_contract = target_entry.manifest.contract if target_entry.manifest is not None else None
        if source_contract is None or target_contract is None or not source_contract.output_schema_ref or not target_contract.input_schema_ref:
            return [], []
        source_schema = self._schema_registry.resolve(source_contract.output_schema_ref)
        target_schema = self._schema_registry.resolve(target_contract.input_schema_ref)
        source_fields = self._flatten_object_schema(source_schema)
        target_fields = self._flatten_object_schema(target_schema)
        if not source_fields or not target_fields:
            return [], []
        suggestions: list[SuggestedStepMapping] = []
        unresolved: list[str] = []
        existing_top_fields = set(existing_inputs.keys())
        for target_field, target_field_schema in target_fields.items():
            if target_field in explicit_target_fields or target_field.split(".")[0] in existing_top_fields:
                continue
            required = self._is_required_field(target_schema, target_field)
            best = None
            for source_field, source_field_schema in source_fields.items():
                if not self._schemas_compatible(source_field_schema, target_field_schema):
                    continue
                confidence = self._mapping_confidence(source_field, target_field)
                if confidence is None:
                    continue
                score = 2 if confidence == "high" else 1
                if best is None or score > best[0]:
                    best = (score, confidence, source_field)
            if best is not None:
                _score, confidence, source_field = best
                suggestions.append(
                    SuggestedStepMapping(
                        step_id=step_id,
                        target_field=target_field,
                        from_step=source_step_id,
                        field=source_field,
                        confidence=confidence,
                        reason="schema name/type match",
                    )
                )
            elif required:
                unresolved.append(target_field)
        return suggestions, unresolved

    def _apply_suggested_mappings(self, compiled_inputs: dict, suggestions: list[SuggestedStepMapping]) -> None:
        for suggestion in suggestions:
            if suggestion.confidence != "high":
                continue
            self._apply_step_mapping(
                compiled_inputs,
                StepMappingDefinition(
                    from_step=suggestion.from_step,
                    field=suggestion.field,
                    target_field=suggestion.target_field,
                ),
            )

    def _flatten_object_schema(self, schema: dict | None, prefix: str = "") -> dict[str, dict]:
        if not isinstance(schema, dict) or schema.get("type") != "object":
            return {}
        result: dict[str, dict] = {}
        for key, child in schema.get("properties", {}).items():
            path = key if not prefix else f"{prefix}.{key}"
            if isinstance(child, dict):
                result[path] = child
                if child.get("type") == "object":
                    result.update(self._flatten_object_schema(child, path))
        return result

    def _is_required_field(self, schema: dict | None, path: str) -> bool:
        if not isinstance(schema, dict):
            return False
        current = schema
        parts = path.split(".")
        for index, part in enumerate(parts):
            required = current.get("required", []) if isinstance(current, dict) else []
            if part not in required:
                return False
            properties = current.get("properties", {}) if isinstance(current, dict) else {}
            child = properties.get(part)
            if child is None:
                return False
            if index == len(parts) - 1:
                return True
            current = child
        return False

    def _normalize_field_name(self, value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    def _mapping_confidence(self, source_field: str, target_field: str) -> str | None:
        if source_field == target_field:
            return "high"
        if self._normalize_field_name(source_field) == self._normalize_field_name(target_field):
            return "medium"
        return None

    def _schemas_compatible(self, source_schema: dict, target_schema: dict) -> bool:
        source_type = source_schema.get("type") if isinstance(source_schema, dict) else None
        target_type = target_schema.get("type") if isinstance(target_schema, dict) else None
        if source_type is None or target_type is None:
            return True
        if source_type == target_type:
            return True
        if source_type == "integer" and target_type == "number":
            return True
        return False

    def _apply_step_mapping(self, compiled_inputs: dict, mapping: StepMappingDefinition) -> None:
        if not mapping.from_step and not mapping.from_inputs and mapping.default_value is None:
            raise SkillFactoryError(
                f"Step mapping for target '{mapping.target_field}' requires from_step or from_inputs (or default_value for literal injection)"
            )
        if mapping.from_step and mapping.from_inputs:
            raise SkillFactoryError(f"Step mapping for target '{mapping.target_field}' cannot set both from_step and from_inputs")
        if mapping.transform and mapping.transform not in {"lowercase", "uppercase", "stringify", "wrap_object"}:
            raise SkillFactoryError(f"Unsupported transform '{mapping.transform}' for target '{mapping.target_field}'")
        reference: dict[str, object]
        if mapping.default_value is not None and not mapping.from_step and not mapping.from_inputs:
            reference = {"$literal": mapping.default_value}
        else:
            reference = {}
            if mapping.from_step:
                reference["$from_step"] = mapping.from_step
            if mapping.from_inputs:
                reference["$from_inputs"] = mapping.from_inputs
            if mapping.field:
                reference["field"] = mapping.field
            if mapping.default_value is not None:
                reference["default"] = mapping.default_value
        if mapping.transform:
            reference["transform"] = mapping.transform
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

    def _assert_generated_app_safe(self, entry: SkillRegistryEntry) -> None:
        manifest = entry.manifest
        if manifest is None:
            return
        risk = manifest.risk
        policy_reasons: list[str] = []
        if risk.risk_level in BLOCKED_GENERATED_APP_RISK_LEVELS:
            policy_reasons.append(f"risk_level={risk.risk_level}")
        if risk.allow_shell:
            policy_reasons.append("allow_shell=true")
        if risk.allow_network:
            policy_reasons.append("allow_network=true")
        if risk.allow_filesystem_write:
            policy_reasons.append("allow_filesystem_write=true")
        if policy_reasons:
            active_override = self._risk_policy.get_active_override(entry.skill_id, scope="generated_app_assembly")
            if active_override is not None:
                return
            self._risk_policy.record_event(
                skill_id=entry.skill_id,
                event_type="policy_blocked",
                actor="system",
                reason="generated app assembly blocked by default risk policy",
                details={
                    "risk_level": risk.risk_level,
                    "policy_reasons": policy_reasons,
                },
            )
            raise _diagnostic(
                "assemble",
                "policy_blocked",
                f"Skill '{entry.skill_id}' is gated from generated app assembly due to risk policy",
                retryable=False,
                hint="Use a lower-risk skill profile or add an explicit future approval/policy layer before assembling this generated app.",
                details={
                    "skill_id": entry.skill_id,
                    "risk_level": risk.risk_level,
                    "policy_reasons": policy_reasons,
                    "override_scope": "generated_app_assembly",
                },
                suggested_retry_request={
                    "blocked_skill_id": entry.skill_id,
                    "replace_with": "lower-risk skill or future approved override",
                },
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
