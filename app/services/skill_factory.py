from __future__ import annotations

from copy import deepcopy

from app.models.app_blueprint import AppBlueprint
from app.models.skill_blueprint import SkillBlueprint
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_creation import AppFromSkillsRequest, AppFromSkillsResult, GeneratedSkillRevisionRequest, GeneratedSkillRevisionResult, GeneratedSkillVersionComparison, SkillCreationRequest, SkillCreationResult, StepMappingDefinition, SuggestedStepMapping
from app.models.skill_diagnostics import SkillDiagnostic, SkillDiagnosticError
from app.models.skill_runtime import SkillExecutionRequest
from app.services.app_profile_resolver import AppProfileResolverService
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
        app_profile_resolver: AppProfileResolverService | None = None,
    ) -> None:
        self._skill_control = skill_control
        self._skill_runtime = skill_runtime
        self._schema_registry = schema_registry
        self._authoring = authoring or SkillAuthoringService()
        self._generated_assets = generated_assets
        self._callable_materializer = callable_materializer or GeneratedCallableMaterializer()
        self._risk_policy = risk_policy or SkillRiskPolicyService()
        self._app_profile_resolver = app_profile_resolver or AppProfileResolverService(skill_control=self._skill_control)

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

    def build_creation_request_from_blueprint(
        self,
        blueprint: SkillBlueprint,
        *,
        adapter_kind: str = "callable",
        generation_operation: str | None = None,
        handler_entry: str | None = None,
        description: str | None = None,
        smoke_test_inputs: dict | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        error_schema: dict | None = None,
    ) -> SkillCreationRequest:
        defaults = self.build_creation_defaults_from_blueprint(blueprint)
        return SkillCreationRequest(
            skill_id=blueprint.skill_id,
            name=blueprint.name,
            description=description or blueprint.goal,
            adapter_kind=adapter_kind,
            capability_profile=defaults["capability_profile"],
            manifest_risk=defaults["manifest_risk"],
            generation_operation=generation_operation,
            handler_entry=handler_entry or "",
            smoke_test_inputs=smoke_test_inputs or {},
            schemas={
                "input": input_schema or {"type": "object", "properties": {}, "additionalProperties": True},
                "output": output_schema or {"type": "object", "properties": {}, "additionalProperties": True},
                "error": error_schema or {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": True,
                },
            },
        )

    def revise_generated_skill(self, skill_id: str, request: GeneratedSkillRevisionRequest) -> GeneratedSkillRevisionResult:
        if self._generated_assets is None:
            raise SkillFactoryError("Generated skill revision requires generated asset storage")
        existing_asset = self._generated_assets.get_generated_asset(skill_id)
        if existing_asset is None:
            raise SkillFactoryError(f"Generated skill asset not found: {skill_id}")
        existing_entry = self._skill_control.get_skill(skill_id)
        if existing_entry.origin != "generated":
            raise SkillFactoryError(f"Only generated skills support revise: {skill_id}")

        schema_payload = request.schemas.model_dump(mode="json")
        revised_request = SkillCreationRequest(
            skill_id=skill_id,
            name=existing_asset.get("name", existing_entry.name),
            description=request.description or existing_asset.get("description", ""),
            adapter_kind=existing_asset.get("adapter_kind", existing_entry.runtime_adapter),
            generation_operation=request.generation_operation or existing_asset.get("generation_operation", ""),
            handler_entry=request.handler_entry or existing_asset.get("handler_entry", ""),
            command=list(request.command or existing_asset.get("command", [])),
            tags=list(request.tags or existing_asset.get("tags", [])),
            capability_profile=request.capability_profile or existing_entry.capability_profile,
            manifest_risk=request.manifest_risk or existing_entry.manifest.risk,
            schemas=schema_payload if schema_payload != {"input": {}, "output": {}, "error": {}} else existing_asset.get("schemas", {}),
            smoke_test_inputs=dict(request.smoke_test_inputs or {}),
        )
        previous_version = existing_entry.active_version
        schema_refs = self._register_contracts(revised_request)
        entry = self._build_entry_and_register_runtime(revised_request, schema_refs)
        prior_versions = []
        for item in existing_entry.versions:
            updated = item.model_copy(deep=True)
            if updated.version == existing_entry.active_version and request.approve_immediately:
                updated.revision_status = "superseded"
            prior_versions.append(updated)
        entry.versions = prior_versions + [
            SkillVersion(
                version=request.version,
                content=entry.versions[-1].content,
                note=request.note or f"revise {request.version}",
                revision_status="active" if request.approve_immediately else "draft",
                reason=request.reason,
                reviewer=request.reviewer,
            )
        ]
        entry.active_version = request.version if request.approve_immediately else existing_entry.active_version
        if entry.manifest is not None:
            entry.manifest.version = entry.active_version
        self._skill_control.register(entry)
        smoke = self._run_smoke_test(revised_request)
        self._generated_assets.persist_generated_skill(request=revised_request, schema_refs=schema_refs, entry=entry, version_override=request.version)
        return GeneratedSkillRevisionResult(
            skill_id=skill_id,
            version=request.version,
            previous_version=previous_version,
            active_version=entry.active_version,
            runtime_adapter=entry.runtime_adapter,
            schema_refs=schema_refs,
            smoke_test=smoke,
        )

    def activate_generated_skill_revision(self, skill_id: str, version: str, reviewer: str = "") -> dict:
        if self._generated_assets is None:
            raise SkillFactoryError("Generated skill activation requires generated asset storage")
        activate_request = self._generated_assets.build_request_for_version(skill_id, version)
        try:
            existing_entry = self._skill_control.get_skill(skill_id)
        except SkillControlError:
            self.reload_generated_skills()
            existing_entry = self._skill_control.get_skill(skill_id)
        if existing_entry.origin != "generated":
            raise SkillFactoryError(f"Only generated skills support activation: {skill_id}")
        activate_request.smoke_test_inputs = {}
        schema_refs = self._register_contracts(activate_request)
        entry = self._build_entry_and_register_runtime(activate_request, schema_refs)
        updated_versions = []
        for item in existing_entry.versions:
            updated = item.model_copy(deep=True)
            if updated.version == version:
                updated.revision_status = "active"
                if reviewer:
                    updated.reviewer = reviewer
            elif updated.version == existing_entry.active_version:
                updated.revision_status = "superseded"
            updated_versions.append(updated)
        entry.versions = updated_versions
        entry.active_version = version
        if entry.manifest is not None:
            entry.manifest.version = version
        self._skill_control.register(entry)
        return {
            "skill_id": skill_id,
            "activated_version": version,
            "active_version": entry.active_version,
            "runtime_adapter": entry.runtime_adapter,
        }

    def compare_generated_skill_versions(self, skill_id: str, from_version: str, to_version: str) -> GeneratedSkillVersionComparison:
        if self._generated_assets is None:
            raise SkillFactoryError("Generated skill comparison requires generated asset storage")
        entry = self._skill_control.get_skill(skill_id)
        if entry.origin != "generated":
            raise SkillFactoryError(f"Only generated skills support compare: {skill_id}")
        try:
            return self._generated_assets.compare_versions(skill_id, from_version, to_version)
        except ValueError as error:
            raise SkillFactoryError(str(error)) from error

    def rollback_generated_skill(self, skill_id: str, target_version: str, reviewer: str = "", rollback_reason: str = "") -> dict:
        if self._generated_assets is None:
            raise SkillFactoryError("Generated skill rollback requires generated asset storage")
        existing_entry = self._skill_control.get_skill(skill_id)
        if existing_entry.origin != "generated":
            raise SkillFactoryError(f"Only generated skills support rollback: {skill_id}")
        rollback_request = self._generated_assets.build_request_for_version(skill_id, target_version)
        rollback_request.smoke_test_inputs = {}
        schema_refs = self._register_contracts(rollback_request)
        entry = self._build_entry_and_register_runtime(rollback_request, schema_refs)
        updated_versions = []
        for item in existing_entry.versions:
            updated = item.model_copy(deep=True)
            if updated.version == target_version:
                updated.revision_status = "active"
                updated.rollback_reason = rollback_reason
                if reviewer:
                    updated.reviewer = reviewer
            elif updated.version == existing_entry.active_version:
                updated.revision_status = "rolled_back"
            updated_versions.append(updated)
        entry.versions = updated_versions
        entry.active_version = target_version
        if entry.manifest is not None:
            entry.manifest.version = target_version
        self._skill_control.register(entry)
        return {
            "skill_id": skill_id,
            "target_version": target_version,
            "active_version": entry.active_version,
            "runtime_adapter": entry.runtime_adapter,
            "reviewer": reviewer,
            "rollback_reason": rollback_reason,
        }

    def create_skill(self, request: SkillCreationRequest) -> SkillCreationResult:
        schema_refs = self._register_contracts(request)
        entry = self._build_entry_and_register_runtime(request, schema_refs)
        smoke = self._run_smoke_test(request)
        if self._generated_assets is not None:
            self._generated_assets.persist_generated_skill(request=request, schema_refs=schema_refs, entry=entry)
        return SkillCreationResult(
            skill_id=request.skill_id,
            schema_refs=schema_refs,
            runtime_adapter=entry.runtime_adapter,
            smoke_test=smoke,
        )

    def _build_entry_and_register_runtime(self, request: SkillCreationRequest, schema_refs: dict[str, str]) -> SkillRegistryEntry:
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
                manifest_risk=request.manifest_risk,
                origin="generated",
                content=request.description or request.name,
            )
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
            self._skill_control.register(entry)
            self._skill_runtime.register_handler(request.skill_id, handler, entry=entry)
            return entry
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
            manifest_risk=request.manifest_risk,
            origin="generated",
            content=request.description or request.name,
        )
        self._skill_control.register(entry)
        self._skill_runtime.register_handler(request.skill_id, self._script_placeholder, entry=entry)
        return entry

    def _run_smoke_test(self, request: SkillCreationRequest):
        return self._skill_runtime.execute(
            SkillExecutionRequest(
                skill_id=request.skill_id,
                app_instance_id="skill-factory",
                workflow_id="skill-smoke-test",
                step_id="smoke",
                inputs=request.smoke_test_inputs,
                config={},
            )
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
        runtime_profile = self._app_profile_resolver.resolve(list(request.skill_ids))
        execution_mode = "pipeline" if len(runtime_profile.runtime_skills) > 1 else "service"
        if not runtime_profile.direct_start_supported and len(runtime_profile.runtime_skills) <= 1:
            execution_mode = "service"
        app_shape = self._classify_generated_app_shape(list(request.skill_ids), execution_mode=execution_mode)
        role_name = {
            "text_transform": "Generated Text Agent",
            "structured_transform": "Generated Data Agent",
            "pipeline_chain": "Generated Pipeline Agent",
        }.get(app_shape, "Generated Agent")
        task_name = {
            "text_transform": "Transform text input into normalized output",
            "structured_transform": "Transform structured payload into normalized output",
            "pipeline_chain": "Run the generated multi-step pipeline",
        }.get(app_shape, "Run generated workflow")
        overview_title = {
            "text_transform": "Text Transformation Overview",
            "structured_transform": "Structured Transformation Overview",
            "pipeline_chain": "Pipeline Overview",
        }.get(app_shape, "Overview")
        run_title = {
            "text_transform": "Run Text Transformation",
            "structured_transform": "Run Structured Transformation",
            "pipeline_chain": "Run Pipeline",
        }.get(app_shape, "Run Workflow")
        activity_title = {
            "text_transform": "Recent Text Transform Activity",
            "structured_transform": "Recent Structured Transform Activity",
            "pipeline_chain": "Pipeline Activity",
        }.get(app_shape, "Activity")
        action_label = {
            "text_transform": "transform-text",
            "structured_transform": "transform-structured-data",
            "pipeline_chain": "run-pipeline",
        }.get(app_shape, "run-workflow")
        visible_views = ["generated.overview", "generated.run", "generated.activity"]
        activation = "on_demand"
        idle_strategy = "keep_alive" if execution_mode == "service" else "suspend"
        if runtime_profile.invocation_posture == "ask_user":
            idle_strategy = "suspend"

        blueprint = AppBlueprint(
            id=request.blueprint_id,
            name=request.name,
            goal=request.goal,
            app_shape=app_shape,
            roles=[{
                "id": "generated.agent",
                "name": role_name,
                "type": "agent",
                "responsibilities": [task_name, "handle generated skill execution"],
                "visible_views": visible_views,
                "allowed_actions": ["workflow.execute", "workflow.inspect"],
            }],
            tasks=[{
                "id": "task.run_generated_workflow",
                "owner_role": "generated.agent",
                "trigger": "manual",
                "inputs": {"workflow_id": request.workflow_id, "app_shape": app_shape},
                "outputs": {"status": "workflow_status", "steps": "execution_steps"},
                "success_condition": task_name,
            }],
            workflows=[
                {
                    "id": request.workflow_id,
                    "name": request.name,
                    "triggers": ["manual"],
                    "steps": steps,
                }
            ],
            views=[
                {
                    "id": "generated.overview",
                    "name": overview_title,
                    "type": "page",
                    "visible_roles": ["generated.agent"],
                    "components": [
                        {"kind": "summary", "title": request.name, "goal": request.goal},
                        {"kind": "runtime_profile", "profile": runtime_profile.model_dump(mode="json")},
                    ],
                },
                {
                    "id": "generated.run",
                    "name": run_title,
                    "type": "form",
                    "visible_roles": ["generated.agent"],
                    "actions": [{"id": action_label, "kind": "workflow.execute", "workflow_id": request.workflow_id}],
                },
                {
                    "id": "generated.activity",
                    "name": activity_title,
                    "type": "dashboard",
                    "visible_roles": ["generated.agent"],
                    "components": [
                        {"kind": "workflow_status", "workflow_id": request.workflow_id},
                        {"kind": "required_skills", "skill_ids": list(request.skill_ids)},
                    ],
                },
            ],
            required_modules=[],
            required_skills=list(request.skill_ids),
            runtime_profile=runtime_profile.model_dump(mode="json"),
            runtime_policy={
                "execution_mode": execution_mode,
                "activation": activation,
                "restart_policy": "on_failure",
                "persistence_level": "standard" if execution_mode == "service" else "full",
                "idle_strategy": idle_strategy,
            },
        )
        return blueprint, AppFromSkillsResult(
            blueprint_id=request.blueprint_id,
            workflow_id=request.workflow_id,
            required_skills=list(request.skill_ids),
            created_steps=created_steps,
            suggested_mappings=suggested_mappings,
            unresolved_inputs=unresolved_inputs,
        )

    def _classify_generated_app_shape(self, skill_ids: list[str], *, execution_mode: str) -> str:
        if execution_mode == "pipeline" or len(skill_ids) > 1:
            return "pipeline_chain"
        if not skill_ids:
            return "generic"
        try:
            entry = self._skill_control.get_skill(skill_ids[0])
        except Exception:
            return "generic"
        contract = entry.manifest.contract if entry.manifest is not None else None
        input_ref = contract.input_schema_ref if contract is not None else ""
        output_ref = contract.output_schema_ref if contract is not None else ""
        input_schema = self._schema_registry.resolve(input_ref) if input_ref else {}
        output_schema = self._schema_registry.resolve(output_ref) if output_ref else {}
        schema_signals = " ".join([
            " ".join((input_schema.get("properties") or {}).keys()) if isinstance(input_schema, dict) else "",
            " ".join((output_schema.get("properties") or {}).keys()) if isinstance(output_schema, dict) else "",
        ])
        signals = " ".join([
            entry.skill_id,
            entry.name,
            entry.manifest.description if entry.manifest is not None else "",
            " ".join(entry.manifest.tags) if entry.manifest is not None else "",
            schema_signals,
        ]).lower()
        if any(token in signals for token in ["text", "slug", "title", "normalize human", "echo"]):
            return "text_transform"
        if any(token in signals for token in ["object", "json", "payload", "keys", "schema", "structured"]):
            return "structured_transform"
        return "generic"

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
