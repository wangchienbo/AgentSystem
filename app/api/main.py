from fastapi import FastAPI, HTTPException

from app.core.errors import map_domain_error

from app.bootstrap.runtime import build_runtime
from app.bootstrap.skills import bootstrap_builtin_skills
from app.bootstrap.catalog import bootstrap_demo_catalog
from app.services.lifecycle import LifecycleError
from app.services.runtime_host import RuntimeHostError
from app.services.scheduler import SchedulerError
from app.services.supervisor import SupervisorError
from app.services.app_catalog import AppCatalogError
from app.services.app_context_store import AppContextStoreError
from app.services.app_data_store import AppDataStoreError
from app.services.app_registry import AppRegistryError
from app.services.app_refinement import AppRefinementError
from app.services.app_refinement_orchestrator import AppRefinementOrchestratorError
from app.services.app_installer import AppInstallerError
from app.services.app_config_service import AppConfigError
from app.services.event_bus import EventBusError
from app.services.practice_review import PracticeReviewError
from app.services.priority_analysis import PriorityAnalysisError
from app.services.proposal_review import ProposalReviewError
from app.services.self_refinement import SelfRefinementError
from app.services.skill_suggestion import SkillSuggestionError
from app.services.workflow_executor import WorkflowExecutorError
from app.services.workflow_subscription import WorkflowSubscriptionError
from app.services.skill_runtime import SkillRuntimeError
from app.services.context_compaction import ContextCompactionError
from app.models.event_bus import EventSubscription
from app.models.workflow_subscription import WorkflowEventSubscription
from app.models.context_policy import ContextCompactionPolicy
from app.models.patch_proposal import SelfRefinementRequest
from app.models.practice_review import PracticeReviewRequest
from app.models.priority_analysis import PriorityAnalysisRequest
from app.models.proposal_review import ProposalReviewRequest
from app.models.refinement_loop import RefinementFilter, RefinementLoopRequest
from app.models.skill_suggestion import SkillSuggestionRequest
from app.models.app_refinement import SuggestedSkillRefinementRequest, SuggestedSkillRefinementClosureRequest
from app.models.skill_creation import AppFromSkillsInstallRunRequest, AppFromSkillsRequest, BlueprintMaterializationRequest, GeneratedSkillRevisionRequest, SkillCreationRequest
from app.services.skill_factory import SkillFactoryError, _diagnostic
from app.services.requirement_blueprint_builder import RequirementBlueprintBuilderError
from app.models.skill_diagnostics import SkillDiagnostic, SkillDiagnosticError, SkillRetryAdviceRequest
from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint
from app.models.app_blueprint import AppBlueprint
from app.models.demonstration import DemonstrationRecord
from app.models.app_instance import AppInstance
from app.models.interaction import UserCommand
from app.models.registry import AppRegistryEntry
from app.models.scheduling import ScheduleRecord, SupervisionPolicy
from app.services.skill_control import SkillControlError
from app.services.skill_retry_advisor import SkillRetryAdvisorService
from app.services.core_skill_toolchain import (
    CoreAcceptanceReportSkill,
    CoreArchiveSummarySkill,
    CoreCostAnalyzerSkill,
    CoreReplaySelectorSkill,
)
from app.api.operator_filters import build_refinement_filter, build_workflow_observability_filter


app = FastAPI(title="AgentSystem App OS", version="0.1.0")
retry_advisor = SkillRetryAdvisorService()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": "0.1.0"}


@app.post("/prompt-selection/select")
def prompt_selection_select(payload: dict) -> dict:
    return prompt_selection.select_for_prompt(
        app_instance_id=payload["app_instance_id"],
        limit=payload.get("limit", 5),
        query=payload.get("query", ""),
        category=payload.get("category") or None,
        max_prompt_tokens=payload.get("max_prompt_tokens"),
        reserved_output_tokens=payload.get("reserved_output_tokens", 256),
        working_set_token_estimate=payload.get("working_set_token_estimate", 400),
        per_evidence_token_estimate=payload.get("per_evidence_token_estimate", 120),
        strategy=payload.get("strategy", "balanced"),
        include_prompt_assembly=payload.get("include_prompt_assembly", True),
    )


@app.post("/prompt-selection/invoke")
def prompt_selection_invoke(payload: dict) -> dict:
    return prompt_invocation.invoke_with_selection(
        app_instance_id=payload["app_instance_id"],
        query=payload.get("query", ""),
        category=payload.get("category") or None,
        limit=payload.get("limit", 5),
        max_prompt_tokens=payload.get("max_prompt_tokens"),
        reserved_output_tokens=payload.get("reserved_output_tokens", 256),
        working_set_token_estimate=payload.get("working_set_token_estimate", 400),
        per_evidence_token_estimate=payload.get("per_evidence_token_estimate", 120),
        strategy=payload.get("strategy", "balanced"),
        include_prompt_assembly=payload.get("include_prompt_assembly", True),
        extra_payload=payload.get("extra_payload"),
    )


@app.post("/blueprints/validate")
def validate_blueprint(blueprint: AppBlueprint) -> dict[str, object]:
    return blueprint_validation.validate(blueprint)


services = build_runtime()
router = services["router"]
requirement_clarifier = services["requirement_clarifier"]
requirement_blueprint_builder = services["requirement_blueprint_builder"]
skill_control = services["skill_control"]
log_evidence = services["log_evidence"]
experience_store = services["experience_store"]
demonstration_extractor = services["demonstration_extractor"]
runtime_store = services["runtime_store"]
app_data_store = services["app_data_store"]
app_config_service = services["app_config_service"]
system_state_service = services["system_state_service"]
system_audit_service = services["system_audit_service"]
lifecycle = services["lifecycle"]
runtime_host = services["runtime_host"]
app_context_store = services["app_context_store"]
scheduler = services["scheduler"]
event_bus = services["event_bus"]
supervisor = services["supervisor"]
context_skill_service = services["context_skill_service"]
practice_review = services["practice_review"]
skill_suggestion = services["skill_suggestion"]
app_registry = services["app_registry"]
self_refinement = services["self_refinement"]
proposal_review = services["proposal_review"]
priority_analysis = services["priority_analysis"]
refinement_loop = services["refinement_loop"]
refinement_memory = services["refinement_memory"]
refinement_rollout = services["refinement_rollout"]
app_installer = services["app_installer"]
app_catalog = services["app_catalog"]
skill_runtime = services["skill_runtime"]
skill_risk_policy = services["skill_risk_policy"]
skill_factory = services["skill_factory"]
app_refinement = services["app_refinement"]
app_refinement_orchestrator = services["app_refinement_orchestrator"]
workflow_executor = services["workflow_executor"]
workflow_subscription = services["workflow_subscription"]
workflow_observability = services["workflow_observability"]
context_compaction = services["context_compaction"]
interaction_gateway = services["interaction_gateway"]
blueprint_validation = services["blueprint_validation"]
collection_policy_service = services["collection_policy_service"]
upgrade_log_service = services["upgrade_log_service"]
telemetry_service = services["telemetry_service"]
evaluation_summary_service = services["evaluation_summary_service"]
prompt_selection = services["prompt_selection"]
prompt_invocation = services["prompt_invocation"]
core_replay_selector = CoreReplaySelectorSkill(telemetry_service)
core_cost_analyzer = CoreCostAnalyzerSkill(telemetry_service)
core_acceptance_report = CoreAcceptanceReportSkill(evaluation_summary_service)
core_archive_summary = CoreArchiveSummarySkill()

bootstrap_builtin_skills(skill_runtime, services)
bootstrap_demo_catalog(app_registry, app_catalog)

@app.post("/route-requirement")
def route_requirement(payload: dict[str, str]) -> dict:
    text = payload.get("text", "")
    return router.route(text).model_dump()

@app.post("/requirements/clarify")
def clarify_requirement(payload: dict[str, str]) -> dict:
    text = payload.get("text", "")
    return requirement_clarifier.clarify(text).model_dump()

@app.post("/requirements/extract")
def extract_requirement(payload: dict[str, str]) -> dict:
    text = payload.get("text", "")
    return requirement_clarifier.extract(text).model_dump()

@app.post("/requirements/readiness")
def requirement_readiness(payload: dict[str, str]) -> dict:
    text = payload.get("text", "")
    result = requirement_clarifier.readiness(text)
    log_evidence.ingest_clarify_unresolved(
        request_text=text,
        requirement_type=result["requirement_type"],
        readiness=result["readiness"],
        missing_fields=result["missing_fields"],
    )
    return result

@app.post("/requirements/blueprint-draft")
def requirement_blueprint_draft(payload: dict[str, str]) -> dict:
    text = payload.get("text", "")
    spec = requirement_clarifier.clarify(text)
    try:
        return requirement_blueprint_builder.build_blueprint_draft(spec).model_dump(mode="json")
    except RequirementBlueprintBuilderError as error:
        raise map_domain_error(error) from error

@app.get("/skills")
def list_skills() -> list[dict]:
    return [skill.model_dump(mode="json") for skill in skill_control.list_skills()]

@app.get("/skills/{skill_id}")
def get_skill(skill_id: str) -> dict:
    try:
        return skill_control.get_skill(skill_id).model_dump(mode="json")
    except SkillControlError as error:
        raise map_domain_error(error) from error

@app.post("/skills/{skill_id}/replace")
def replace_skill(skill_id: str, payload: dict[str, str]) -> dict:
    try:
        return skill_control.replace_skill(
            skill_id=skill_id,
            version=payload["version"],
            content=payload["content"],
            note=payload.get("note", ""),
        ).model_dump(mode="json")
    except SkillControlError as error:
        raise map_domain_error(error) from error

@app.post("/skills/{skill_id}/rollback")
def rollback_skill(skill_id: str, payload: dict[str, str]) -> dict:
    try:
        entry = skill_control.get_skill(skill_id)
        if entry.origin == "generated":
            return skill_factory.rollback_generated_skill(
                skill_id,
                payload["target_version"],
                reviewer=payload.get("reviewer", ""),
                rollback_reason=payload.get("rollback_reason", ""),
            )
        return skill_control.rollback_skill(skill_id, payload["target_version"]).model_dump(mode="json")
    except (SkillControlError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error

@app.post("/skills/{skill_id}/disable")
def disable_skill(skill_id: str) -> dict:
    try:
        return skill_control.disable_skill(skill_id).model_dump(mode="json")
    except SkillControlError as error:
        raise map_domain_error(error) from error

@app.post("/skills/{skill_id}/enable")
def enable_skill(skill_id: str) -> dict:
    try:
        return skill_control.enable_skill(skill_id).model_dump(mode="json")
    except SkillControlError as error:
        raise map_domain_error(error) from error

@app.post("/skills/create")
def create_skill(request: SkillCreationRequest) -> dict:
    try:
        return skill_factory.create_skill(request).model_dump(mode="json")
    except (SkillDiagnosticError, SkillControlError, SkillRuntimeError, ValueError) as error:
        raise map_domain_error(error) from error

@app.get("/skills/{skill_id}/versions")
def list_skill_versions(skill_id: str) -> list[dict]:
    try:
        entry = skill_control.get_skill(skill_id)
        return [
            {
                "version": item.version,
                "note": item.note,
                "created_at": item.created_at.isoformat(),
                "active": item.version == entry.active_version,
                "revision_status": item.revision_status,
                "reason": item.reason,
                "reviewer": item.reviewer,
                "approved_at": item.approved_at.isoformat() if item.approved_at else None,
                "rollback_reason": item.rollback_reason,
            }
            for item in entry.versions
        ]
    except SkillControlError as error:
        raise map_domain_error(error) from error

@app.get("/skills/{skill_id}/compare")
def compare_skill_versions(skill_id: str, from_version: str, to_version: str) -> dict:
    try:
        entry = skill_control.get_skill(skill_id)
        if entry.origin != "generated":
            raise SkillFactoryError(f"Only generated skills support compare: {skill_id}")
        return skill_factory.compare_generated_skill_versions(skill_id, from_version, to_version).model_dump(mode="json")
    except (SkillControlError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error

@app.post("/skills/{skill_id}/revisions/{version}/activate")
def activate_generated_skill_revision(skill_id: str, version: str, payload: dict[str, str] | None = None) -> dict:
    try:
        reviewer = (payload or {}).get("reviewer", "")
        return skill_factory.activate_generated_skill_revision(skill_id, version, reviewer=reviewer)
    except (SkillControlError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error

@app.post("/skills/{skill_id}/revise")
def revise_generated_skill(skill_id: str, request: GeneratedSkillRevisionRequest) -> dict:
    try:
        return skill_factory.revise_generated_skill(skill_id, request).model_dump(mode="json")
    except (SkillDiagnosticError, SkillControlError, SkillRuntimeError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error

@app.post("/skills/diagnose-retry")
def diagnose_retry(request: SkillRetryAdviceRequest) -> dict:
    return retry_advisor.build_retry_advice(request.diagnostic).model_dump(mode="json")

@app.get("/skill-risk/decisions")
def list_skill_risk_decisions() -> list[dict]:
    return [item.model_dump(mode="json") for item in skill_risk_policy.list_decisions()]

@app.get("/skill-risk/events")
def list_skill_risk_events(skill_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in skill_risk_policy.list_events(skill_id=skill_id)]

@app.get("/skill-risk/stats")
def get_skill_risk_stats() -> dict:
    return skill_risk_policy.get_stats_summary().model_dump(mode="json")

@app.get("/skill-risk/dashboard")
def get_skill_risk_dashboard(recent_limit: int = 5) -> dict:
    return skill_risk_policy.get_dashboard(recent_limit=recent_limit).model_dump(mode="json")

@app.get("/evidence/drafts")
def get_evidence_drafts(limit: int | None = None) -> dict:
    return log_evidence.list_drafts(limit=limit).model_dump(mode="json")

@app.get("/evidence/signals")
def get_evidence_signals(limit: int | None = None) -> dict:
    return log_evidence.list_signals(limit=limit).model_dump(mode="json")

@app.get("/evidence/promoted")
def get_promoted_evidence(limit: int | None = None) -> dict:
    return log_evidence.list_promoted_evidence(limit=limit).model_dump(mode="json")

@app.get("/evidence/index")
def get_evidence_index(limit: int | None = None) -> dict:
    return log_evidence.list_index_entries(limit=limit).model_dump(mode="json")

@app.get("/evidence/stats")
def get_evidence_stats() -> dict:
    return log_evidence.get_stats_summary()

@app.post("/skill-risk/{skill_id}/approve")
def approve_skill_risk_override(
    skill_id: str,
    reviewer: str,
    reason: str = "",
    scope: str = "generated_app_assembly",
) -> dict:
    return skill_risk_policy.approve_override(
        skill_id=skill_id,
        reviewer=reviewer,
        reason=reason,
        scope=scope,
    ).model_dump(mode="json")

@app.post("/skill-risk/{skill_id}/revoke")
def revoke_skill_risk_override(
    skill_id: str,
    reviewer: str,
    reason: str = "",
    scope: str = "generated_app_assembly",
) -> dict:
    return skill_risk_policy.revoke_override(skill_id=skill_id, reviewer=reviewer, reason=reason).model_dump(mode="json")

@app.post("/apps/from-skills")
def create_app_from_skills(request: AppFromSkillsRequest) -> dict:
    try:
        blueprint, result = skill_factory.build_blueprint_from_skills(request)
        app_registry.register_blueprint(blueprint)
        return {
            "blueprint": blueprint.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
    except (SkillDiagnosticError, AppRegistryError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error

@app.post("/apps/from-skills/install-run")
def create_install_and_run_app_from_skills(request: AppFromSkillsInstallRunRequest) -> dict:
    try:
        blueprint, result = skill_factory.build_blueprint_from_skills(request)
        app_registry.register_blueprint(blueprint)
        install = app_installer.install_app(blueprint_id=blueprint.id, user_id=request.user_id)
        execution = workflow_executor.execute_workflow(
            app_instance_id=install.app_instance_id,
            workflow_id=result.workflow_id,
            trigger=request.trigger,
            inputs=request.workflow_inputs,
        )
        if execution.status != "completed":
            first_failure = next((step for step in execution.steps if step.status == "failed"), None)
            raise SkillDiagnosticError(
                SkillDiagnostic(
                    stage="execute",
                    kind="contract_violation" if first_failure and "contract" in str(first_failure.detail).lower() else "execution_error",
                    message="Generated app execution did not complete successfully",
                    retryable=False,
                    hint="Check the failing step detail and align generated inputs/contracts before retrying.",
                    details={
                        "workflow_id": result.workflow_id,
                        "app_instance_id": install.app_instance_id,
                        "failed_step": None if first_failure is None else first_failure.model_dump(mode="json"),
                    },
                    suggested_retry_request={
                        "workflow_id": result.workflow_id,
                        "app_instance_id": install.app_instance_id,
                        "step_inputs": {
                            first_failure.step_id if first_failure is not None else "skill.1": {
                                "text": "replace-with-valid-input"
                            }
                        },
                    },
                )
            )
        return {
            "blueprint": blueprint.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
            "install": install.model_dump(mode="json"),
            "execution": execution.model_dump(mode="json"),
        }
    except (AppInstallerError, LifecycleError, RuntimeHostError, WorkflowExecutorError) as error:
        raise map_domain_error(
            SkillDiagnosticError(
                SkillDiagnostic(
                    stage="install",
                    kind="install_error",
                    message=str(error),
                    retryable=False,
                    hint="Check generated blueprint wiring, required inputs, and install preconditions before retrying.",
                    details={"blueprint_id": request.blueprint_id, "workflow_id": request.workflow_id},
                    suggested_retry_request={
                        "blueprint_id": request.blueprint_id,
                        "workflow_id": request.workflow_id,
                        "step_inputs": {
                            "skill.1": {
                                "text": "replace-with-valid-input"
                            }
                        },
                    },
                )
            )
        ) from error
    except (SkillDiagnosticError, AppRegistryError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error


@app.post("/apps/refine-from-suggested-skills")
def refine_app_from_suggested_skills(request: SuggestedSkillRefinementRequest) -> dict:
    try:
        result = app_refinement.build_app_from_suggested_skills(request)
        app_registry.register_blueprint(result.blueprint)
        return result.model_dump(mode="json")
    except (AppRefinementError, AppRegistryError, SkillDiagnosticError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error


@app.post("/apps/refine-from-suggested-skills/closure")
def refine_app_from_suggested_skills_closure(request: SuggestedSkillRefinementClosureRequest) -> dict:
    try:
        result = app_refinement_orchestrator.refine_closure(request)
        return result.model_dump(mode="json")
    except (AppRefinementError, AppRefinementOrchestratorError, AppRegistryError, SkillDiagnosticError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error

@app.get("/experiences")
def list_experiences() -> list[dict]:
    return [item.model_dump(mode="json") for item in experience_store.list_experiences()]

@app.post("/experiences")
def add_experience(record: ExperienceRecord) -> dict:
    return experience_store.add_experience(record).model_dump(mode="json")

@app.get("/skill-blueprints")
def list_skill_blueprints() -> list[dict]:
    return [item.model_dump(mode="json") for item in experience_store.list_skill_blueprints()]

@app.post("/skill-blueprints")
def add_skill_blueprint(blueprint: SkillBlueprint) -> dict:
    return experience_store.add_skill_blueprint(blueprint).model_dump(mode="json")

@app.post("/skill-blueprints/{skill_id}/materialize")
def materialize_skill_blueprint(skill_id: str, request: BlueprintMaterializationRequest) -> dict:
    try:
        blueprint = experience_store.get_skill_blueprint(skill_id)
        safety_profile = blueprint.safety_profile or {}
        effective_adapter_kind = request.adapter_kind or (
            "callable" if safety_profile.get("prefer_callable_materialization") else "callable"
        )
        if (
            effective_adapter_kind == "script"
            and request.command
            and request.command[0] in {"bash", "sh"}
            and safety_profile.get("allow_shell") is False
        ):
            active_override = skill_risk_policy.get_active_override(skill_id, scope="blueprint_materialization")
            if active_override is None:
                raise _diagnostic(
                    "materialize",
                    "policy_blocked",
                    f"Skill blueprint '{skill_id}' is gated from shell materialization by safety profile",
                    retryable=False,
                    hint="Use callable materialization or provide an explicit policy override for shell-based blueprint materialization.",
                    details={
                        "skill_id": skill_id,
                        "adapter_kind": request.adapter_kind,
                        "command": request.command,
                        "policy_reasons": ["blueprint.allow_shell=false"],
                        "override_scope": "blueprint_materialization",
                    },
                )
        creation_request = skill_factory.build_creation_request_from_blueprint(
            blueprint,
            adapter_kind=effective_adapter_kind,
            generation_operation=request.generation_operation,
            handler_entry=request.handler_entry,
            description=request.description,
            smoke_test_inputs=request.smoke_test_inputs,
            input_schema=request.schemas.input,
            output_schema=request.schemas.output,
            error_schema=request.schemas.error,
        )
        creation_request.command = request.command
        creation_request.tags = request.tags
        if (
            effective_adapter_kind == "script"
            and request.command
            and request.command[0] in {"bash", "sh"}
        ):
            active_override = skill_risk_policy.get_active_override(skill_id, scope="blueprint_materialization")
            if active_override is not None:
                creation_request.manifest_risk.allow_shell = True
                creation_request.manifest_risk.risk_level = "R2_shell"
                creation_request.capability_profile.risk_level = "R2_shell"
        creation_result = skill_factory.create_skill(creation_request)
        registered_skill = skill_control.get_skill(creation_result.skill_id)
        return {
            "skill_blueprint": blueprint.model_dump(mode="json"),
            "creation_request": creation_request.model_dump(mode="json"),
            "creation_result": creation_result.model_dump(mode="json"),
            "registered_skill": registered_skill.model_dump(mode="json"),
        }
    except (KeyError, SkillFactoryError, SkillDiagnosticError, ValueError) as error:
        raise map_domain_error(error) from error

@app.get("/experiences/{experience_id}/suggested-skills")
def suggest_skills_for_experience(experience_id: str) -> list[dict]:
    return [
        item.model_dump(mode="json")
        for item in experience_store.suggest_skills_for_experience(experience_id)
    ]

@app.post("/demonstrations/extract")
def extract_demonstration(record: DemonstrationRecord) -> dict:
    experience, skill = demonstration_extractor.extract(record)
    experience_store.add_experience(experience)
    experience_store.add_skill_blueprint(skill)
    return {
        "experience": experience.model_dump(mode="json"),
        "skill_blueprint": skill.model_dump(mode="json"),
    }


@app.get("/apps")
def list_apps() -> list[dict]:
    return [item.model_dump(mode="json") for item in lifecycle.list_instances()]


@app.post("/apps")
def create_app_instance(instance: AppInstance) -> dict:
    runtime_host.register_instance(instance)
    return instance.model_dump(mode="json")


@app.get("/apps/{app_instance_id}")
def get_app_instance(app_instance_id: str) -> dict:
    try:
        return lifecycle.get_instance(app_instance_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError) as error:
        raise map_domain_error(error) from error


@app.get("/apps/{app_instance_id}/events")
def list_app_events(app_instance_id: str) -> list[dict]:
    try:
        return [item.model_dump(mode="json") for item in lifecycle.list_events(app_instance_id)]
    except (LifecycleError, RuntimeHostError) as error:
        raise map_domain_error(error) from error


@app.post("/apps/{app_instance_id}/actions/{action}")
def apply_app_action(app_instance_id: str, action: str, payload: dict | None = None) -> dict:
    reason = (payload or {}).get("reason", "")
    try:
        if action == "validate":
            return lifecycle.transition(app_instance_id, "validate", reason=reason).model_dump(mode="json")
        if action == "compile":
            return lifecycle.transition(app_instance_id, "compile", reason=reason).model_dump(mode="json")
        if action == "install":
            return lifecycle.transition(app_instance_id, "install", reason=reason).model_dump(mode="json")
        if action == "upgrade":
            return lifecycle.transition(app_instance_id, "upgrade", reason=reason).model_dump(mode="json")
        if action == "archive":
            return lifecycle.transition(app_instance_id, "archive", reason=reason).model_dump(mode="json")
        if action == "start":
            return runtime_host.start(app_instance_id, reason=reason).model_dump(mode="json")
        if action == "pause":
            return runtime_host.pause(app_instance_id, reason=reason).model_dump(mode="json")
        if action == "resume":
            return runtime_host.resume(app_instance_id, reason=reason).model_dump(mode="json")
        if action == "stop":
            return runtime_host.stop(app_instance_id, reason=reason).model_dump(mode="json")
        if action == "fail":
            return runtime_host.mark_failed(app_instance_id, reason=reason).model_dump(mode="json")
        raise map_domain_error(LifecycleError(f"Unsupported app action: {action}"))
    except (LifecycleError, RuntimeHostError) as error:
        raise map_domain_error(error) from error


@app.post("/apps/{app_instance_id}/tasks")
def enqueue_runtime_task(app_instance_id: str, payload: dict[str, str]) -> dict:
    try:
        tasks = runtime_host.enqueue_task(app_instance_id, payload["task_name"])
        return {"app_instance_id": app_instance_id, "pending_tasks": tasks}
    except (LifecycleError, RuntimeHostError) as error:
        raise map_domain_error(error) from error


@app.post("/apps/{app_instance_id}/healthcheck")
def healthcheck_app(app_instance_id: str, payload: dict[str, bool] | None = None) -> dict:
    healthy = True if payload is None else payload.get("healthy", True)
    try:
        return runtime_host.healthcheck(app_instance_id, healthy=healthy).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError) as error:
        raise map_domain_error(error) from error


@app.get("/apps/{app_instance_id}/runtime")
def get_runtime_overview(app_instance_id: str) -> dict:
    try:
        return runtime_host.get_overview(app_instance_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError) as error:
        raise map_domain_error(error) from error


@app.get("/registry/apps")
def list_registry_apps() -> list[dict]:
    return [item.model_dump(mode="json") for item in app_registry.list_entries()]


@app.get("/registry/apps/{blueprint_id}/releases")
def list_app_releases(blueprint_id: str) -> list[dict]:
    try:
        entry = next(item for item in app_registry.list_entries() if item.blueprint_id == blueprint_id)
        return [item.model_dump(mode="json") for item in entry.releases]
    except StopIteration as error:
        raise HTTPException(status_code=404, detail=f"App blueprint not found: {blueprint_id}") from error


@app.get("/registry/apps/{blueprint_id}/release-history")
def get_app_release_history(blueprint_id: str) -> dict:
    try:
        return app_registry.get_release_history(blueprint_id).model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.get("/registry/apps/{blueprint_id}/summary")
def get_app_control_plane_summary(blueprint_id: str) -> dict:
    try:
        return app_registry.get_control_plane_summary(blueprint_id).model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.get("/registry/apps/overview")
def get_app_registry_overview(
    app_shape: str | None = None,
    has_draft: bool | None = None,
    rollback_available: bool | None = None,
    limit: int | None = None,
) -> dict:
    return app_registry.get_registry_overview(
        app_shape=app_shape,
        has_draft=has_draft,
        rollback_available=rollback_available,
        limit=limit,
    ).model_dump(mode="json")


@app.get("/registry/apps/attention")
def get_app_registry_attention(limit: int | None = None) -> dict:
    return app_registry.get_attention_summary(limit=limit).model_dump(mode="json")


@app.post("/registry/apps/{blueprint_id}/attention-actions")
def record_app_attention_action(blueprint_id: str, payload: dict[str, str]) -> dict:
    try:
        return app_registry.record_operator_action(
            blueprint_id=blueprint_id,
            attention_reason=payload["attention_reason"],
            action=payload["action"],
            reviewer=payload.get("reviewer", ""),
            note=payload.get("note", ""),
        ).model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.get("/registry/apps/{blueprint_id}/compare")
def compare_app_releases(blueprint_id: str, from_version: str, to_version: str) -> dict:
    try:
        return app_registry.compare_releases(blueprint_id, from_version, to_version).model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.post("/registry/apps/{blueprint_id}/releases")
def add_app_release(blueprint_id: str, payload: dict) -> dict:
    try:
        entry = app_registry.add_release(
            blueprint_id,
            version=payload["version"],
            note=payload.get("note", ""),
            reviewer=payload.get("reviewer", ""),
            activate_immediately=payload.get("activate_immediately", False),
        )
        return entry.model_dump(mode="json")
    except (ValueError, HTTPException) as error:
        raise map_domain_error(error) if isinstance(error, ValueError) else error


@app.post("/registry/apps/{blueprint_id}/releases/{version}/activate")
def activate_app_release(blueprint_id: str, version: str, payload: dict | None = None) -> dict:
    try:
        entry = app_registry.activate_release(blueprint_id, version, reviewer=(payload or {}).get("reviewer", ""))
        return entry.model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.post("/registry/apps/{blueprint_id}/rollback")
def rollback_app_release(blueprint_id: str, payload: dict) -> dict:
    try:
        entry = app_registry.rollback_release(
            blueprint_id,
            payload["target_version"],
            reviewer=payload.get("reviewer", ""),
            rollback_reason=payload.get("rollback_reason", ""),
        )
        return entry.model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.post("/registry/apps")
def register_blueprint(blueprint: AppBlueprint) -> dict:
    try:
        return app_registry.register_blueprint(blueprint).model_dump(mode="json")
    except (AppRegistryError,) as error:
        raise map_domain_error(error) from error


@app.post("/registry/apps/{blueprint_id}/install")
def install_blueprint(blueprint_id: str, payload: dict[str, str]) -> dict:
    try:
        return app_installer.install_app(blueprint_id=blueprint_id, user_id=payload["user_id"]).model_dump(mode="json")
    except (AppRegistryError, AppInstallerError, LifecycleError, RuntimeHostError) as error:
        raise map_domain_error(error) from error


@app.get("/catalog/apps")
def list_catalog_apps() -> list[dict]:
    return [item.model_dump(mode="json") for item in app_catalog.list_apps()]


@app.post("/interaction/command")
def handle_user_command(command: UserCommand) -> dict:
    try:
        return interaction_gateway.handle_command(command).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, AppCatalogError) as error:
        raise map_domain_error(error) from error


@app.post("/apps/{app_instance_id}/workflows/execute")
def execute_primary_workflow(app_instance_id: str, payload: dict | None = None) -> dict:
    try:
        payload = payload or {}
        return workflow_executor.execute_workflow(
            app_instance_id=app_instance_id,
            workflow_id=payload.get("workflow_id"),
            trigger=payload.get("trigger", "manual"),
            inputs=payload.get("inputs", {}),
        ).model_dump(mode="json")
    except (LifecycleError, WorkflowExecutorError, AppRegistryError) as error:
        raise map_domain_error(error) from error


@app.get("/workflows/history")
def list_workflow_history(app_instance_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in workflow_executor.list_history(app_instance_id)]


@app.get("/workflows/failures")
def list_workflow_failures(
    app_instance_id: str | None = None,
    workflow_id: str | None = None,
    failed_step_id: str | None = None,
) -> list[dict]:
    failures = workflow_executor.list_recent_failures(app_instance_id)
    if workflow_id is not None:
        failures = [item for item in failures if item.workflow_id == workflow_id]
    if failed_step_id is not None:
        failures = [item for item in failures if failed_step_id in item.failed_step_ids]
    return [item.model_dump(mode="json") for item in failures]


@app.get("/workflows/latest")
def get_latest_workflow_execution(app_instance_id: str | None = None) -> dict:
    history = workflow_executor.list_history(app_instance_id)
    if not history:
        return {"execution": None}
    latest = max(history, key=lambda item: item.completed_at)
    return {"execution": latest.model_dump(mode="json")}


@app.post("/apps/{app_instance_id}/workflows/retry-last-failure")
def retry_last_failed_workflow(app_instance_id: str) -> dict:
    try:
        return workflow_executor.retry_last_failure(app_instance_id).model_dump(mode="json")
    except (WorkflowExecutorError,) as error:
        raise map_domain_error(error) from error


@app.post("/apps/{app_instance_id}/workflows/resume-last-interrupted")
def resume_last_interrupted_workflow(app_instance_id: str, payload: dict | None = None) -> dict:
    try:
        payload = payload or {}
        return workflow_executor.resume_last_interrupted(
            app_instance_id,
            resume_inputs=payload.get("resume_inputs", {}),
        ).model_dump(mode="json")
    except (WorkflowExecutorError,) as error:
        raise map_domain_error(error) from error


@app.get("/workflows/diagnostics")
def get_workflow_diagnostics(
    app_instance_id: str,
    workflow_id: str | None = None,
    failed_step_id: str | None = None,
) -> dict:
    filters = build_workflow_observability_filter(
        app_instance_id=app_instance_id,
        workflow_id=workflow_id,
        failed_step_id=failed_step_id,
    )
    return workflow_observability.get_diagnostics_summary(
        app_instance_id=filters.app_instance_id,
        workflow_id=filters.workflow_id,
        failed_step_id=filters.failed_step_id,
    ).model_dump(mode="json")


@app.get("/workflows/latest-recovery")
def get_latest_workflow_recovery(app_instance_id: str, workflow_id: str | None = None) -> dict:
    recovery = workflow_observability.get_latest_recovery_summary(app_instance_id, workflow_id=workflow_id)
    return {"recovery": None if recovery is None else recovery.model_dump(mode="json")}


@app.get("/workflows/overview")
def get_workflow_overview(app_instance_id: str, workflow_id: str | None = None, failed_step_id: str | None = None) -> dict:
    filters = build_workflow_observability_filter(
        app_instance_id=app_instance_id,
        workflow_id=workflow_id,
        failed_step_id=failed_step_id,
    )
    return workflow_observability.get_overview(
        app_instance_id=filters.app_instance_id,
        workflow_id=filters.workflow_id,
        failed_step_id=filters.failed_step_id,
    ).model_dump(mode="json")


@app.get("/workflows/observability-history")
def list_workflow_observability_history(
    app_instance_id: str,
    workflow_id: str | None = None,
    failed_step_id: str | None = None,
    limit: int | None = None,
    unresolved_only: bool = False,
    since: str | None = None,
    cursor: str | None = None,
) -> dict:
    filters = build_workflow_observability_filter(
        app_instance_id=app_instance_id,
        workflow_id=workflow_id,
        failed_step_id=failed_step_id,
        limit=limit,
        unresolved_only=unresolved_only,
        since=since,
        cursor=cursor,
    )
    return workflow_observability.list_observability_history(
        app_instance_id=filters.app_instance_id,
        workflow_id=filters.workflow_id,
        failed_step_id=filters.failed_step_id,
        limit=filters.limit,
        unresolved_only=filters.unresolved_only,
        since=filters.since,
        cursor=filters.cursor,
    ).model_dump(mode="json")


@app.get("/workflows/timeline")
def list_workflow_timeline(
    app_instance_id: str,
    workflow_id: str | None = None,
    failed_step_id: str | None = None,
    limit: int | None = None,
    unresolved_only: bool = False,
    since: str | None = None,
    cursor: str | None = None,
) -> dict:
    filters = build_workflow_observability_filter(
        app_instance_id=app_instance_id,
        workflow_id=workflow_id,
        failed_step_id=failed_step_id,
        limit=limit,
        unresolved_only=unresolved_only,
        since=since,
        cursor=cursor,
    )
    return workflow_observability.list_timeline_events(
        app_instance_id=filters.app_instance_id,
        workflow_id=filters.workflow_id,
        failed_step_id=filters.failed_step_id,
        limit=filters.limit,
        unresolved_only=filters.unresolved_only,
        since=filters.since,
        cursor=filters.cursor,
    ).model_dump(mode="json")


@app.get("/workflows/stats")
def get_workflow_stats(
    app_instance_id: str,
    workflow_id: str | None = None,
    failed_step_id: str | None = None,
    since: str | None = None,
) -> dict:
    filters = build_workflow_observability_filter(
        app_instance_id=app_instance_id,
        workflow_id=workflow_id,
        failed_step_id=failed_step_id,
        since=since,
    )
    return workflow_observability.get_stats_summary(
        app_instance_id=filters.app_instance_id,
        workflow_id=filters.workflow_id,
        failed_step_id=filters.failed_step_id,
        since=filters.since,
    ).model_dump(mode="json")


@app.get("/workflows/dashboard")
def get_workflow_dashboard(
    app_instance_id: str,
    workflow_id: str | None = None,
    failed_step_id: str | None = None,
    since: str | None = None,
    timeline_limit: int = 5,
) -> dict:
    filters = build_workflow_observability_filter(
        app_instance_id=app_instance_id,
        workflow_id=workflow_id,
        failed_step_id=failed_step_id,
        since=since,
    )
    return workflow_observability.get_dashboard_summary(
        app_instance_id=filters.app_instance_id,
        workflow_id=filters.workflow_id,
        failed_step_id=filters.failed_step_id,
        since=filters.since,
        timeline_limit=timeline_limit,
    ).model_dump(mode="json")


@app.get("/runtime/persistence")
def get_runtime_persistence_snapshot() -> dict:
    return {
        "app_instances": runtime_store.load_json("app_instances", {}),
        "lifecycle_events": runtime_store.load_json("lifecycle_events", {}),
        "runtime_leases": runtime_store.load_json("runtime_leases", {}),
        "runtime_checkpoints": runtime_store.load_json("runtime_checkpoints", {}),
        "runtime_pending_tasks": runtime_store.load_json("runtime_pending_tasks", {}),
        "runtime_schedules": runtime_store.load_json("runtime_schedules", {}),
        "supervision_policies": runtime_store.load_json("supervision_policies", {}),
        "supervision_statuses": runtime_store.load_json("supervision_statuses", {}),
        "registry_entries": runtime_store.load_json("registry_entries", {}),
        "registry_blueprints": runtime_store.load_json("registry_blueprints", {}),
        "data_namespaces": runtime_store.load_json("data_namespaces", {}),
        "data_records": runtime_store.load_json("data_records", {}),
        "event_log": runtime_store.load_json("event_log", []),
        "event_subscriptions": runtime_store.load_json("event_subscriptions", {}),
        "patch_proposals": runtime_store.load_json("patch_proposals", {}),
        "proposal_reviews": runtime_store.load_json("proposal_reviews", {}),
        "app_contexts": runtime_store.load_json("app_contexts", {}),
        "context_summaries": runtime_store.load_json("context_summaries", {}),
        "context_policies": runtime_store.load_json("context_policies", {}),
    }


@app.get("/app-contexts")
def list_app_contexts() -> list[dict]:
    return [item.model_dump(mode="json") for item in app_context_store.list_contexts()]


@app.get("/app-contexts/{app_instance_id}")
def get_app_context(app_instance_id: str, include_runtime: bool = False) -> dict:
    try:
        if include_runtime:
            view = app_context_store.get_runtime_view(app_instance_id)
            return {
                "context": view["context"].model_dump(mode="json"),
                "runtime": None if view["runtime"] is None else view["runtime"].model_dump(mode="json"),
            }
        return app_context_store.get_context(app_instance_id).model_dump(mode="json")
    except AppContextStoreError as error:
        raise map_domain_error(error) from error


@app.post("/app-contexts/{app_instance_id}")
def update_app_context(app_instance_id: str, payload: dict) -> dict:
    try:
        return app_context_store.update_context(
            app_instance_id=app_instance_id,
            current_goal=payload.get("current_goal"),
            current_stage=payload.get("current_stage"),
        ).model_dump(mode="json")
    except AppContextStoreError as error:
        raise map_domain_error(error) from error


@app.post("/app-contexts/{app_instance_id}/entries")
def append_app_context_entry(app_instance_id: str, payload: dict) -> dict:
    try:
        return app_context_store.append_entry(
            app_instance_id=app_instance_id,
            section=payload["section"],
            key=payload["key"],
            value=payload.get("value"),
            tags=payload.get("tags", []),
        ).model_dump(mode="json")
    except AppContextStoreError as error:
        raise map_domain_error(error) from error


@app.post("/app-contexts/{app_instance_id}/compact")
def compact_app_context(app_instance_id: str) -> dict:
    try:
        return context_compaction.compact(app_instance_id).model_dump(mode="json")
    except (AppContextStoreError, ContextCompactionError) as error:
        raise map_domain_error(error) from error


@app.get("/app-contexts/{app_instance_id}/working-set")
def get_app_working_set(app_instance_id: str) -> dict:
    try:
        return context_compaction.build_working_set(app_instance_id).model_dump(mode="json")
    except (AppContextStoreError, ContextCompactionError) as error:
        raise map_domain_error(error) from error


@app.get("/app-contexts/{app_instance_id}/layers")
def get_app_context_layers(app_instance_id: str) -> dict:
    try:
        return context_compaction.list_layers(app_instance_id)
    except (AppContextStoreError, ContextCompactionError) as error:
        raise map_domain_error(error) from error


@app.post("/app-contexts/{app_instance_id}/policy")
def set_app_context_policy(app_instance_id: str, payload: dict) -> dict:
    try:
        return context_compaction.set_policy(
            ContextCompactionPolicy(
                app_instance_id=app_instance_id,
                max_context_entries=payload.get("max_context_entries", 20),
                compact_on_workflow_complete=payload.get("compact_on_workflow_complete", True),
                compact_on_workflow_failure=payload.get("compact_on_workflow_failure", True),
                compact_on_stage_change=payload.get("compact_on_stage_change", False),
            )
        ).model_dump(mode="json")
    except ContextCompactionError as error:
        raise map_domain_error(error) from error


@app.get("/data/namespaces")
def list_data_namespaces(app_instance_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in app_data_store.list_namespaces(app_instance_id)]


@app.get("/data/namespaces/{namespace_id}")
def get_data_namespace(namespace_id: str) -> dict:
    try:
        return app_data_store.get_namespace(namespace_id).model_dump(mode="json")
    except AppDataStoreError as error:
        raise map_domain_error(error) from error


@app.get("/data/namespaces/{namespace_id}/records")
def list_data_records(namespace_id: str) -> list[dict]:
    try:
        return [item.model_dump(mode="json") for item in app_data_store.list_records(namespace_id)]
    except AppDataStoreError as error:
        raise map_domain_error(error) from error


@app.post("/data/namespaces/{namespace_id}/records")
def put_data_record(namespace_id: str, payload: dict) -> dict:
    try:
        return app_data_store.put_record(
            namespace_id=namespace_id,
            key=payload["key"],
            value=payload.get("value", {}),
            tags=payload.get("tags", []),
        ).model_dump(mode="json")
    except AppDataStoreError as error:
        raise map_domain_error(error) from error


@app.get("/events")
def list_events(event_name: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in event_bus.list_events(event_name)]


@app.post("/events/publish")
def publish_event(payload: dict) -> dict:
    try:
        result = event_bus.publish(
            event_name=payload["event_name"],
            source=payload.get("source", "system"),
            app_instance_id=payload.get("app_instance_id"),
            payload=payload.get("payload", {}),
        )
        workflow_runs = workflow_subscription.trigger(
            event_name=payload["event_name"],
            payload=payload.get("payload", {}),
        )
        response = result.model_dump(mode="json")
        response["workflow_runs"] = [item.model_dump(mode="json") for item in workflow_runs]
        return response
    except (EventBusError, WorkflowSubscriptionError, WorkflowExecutorError, AppRegistryError, LifecycleError) as error:
        raise map_domain_error(error) from error


@app.get("/events/subscriptions")
def list_event_subscriptions(event_name: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in scheduler.list_subscriptions(event_name)]


@app.post("/events/subscriptions")
def create_event_subscription(subscription: EventSubscription) -> dict:
    try:
        return event_bus.subscribe(subscription).model_dump(mode="json")
    except EventBusError as error:
        raise map_domain_error(error) from error


@app.get("/workflow-subscriptions")
def list_workflow_subscriptions(event_name: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in workflow_subscription.list_subscriptions(event_name)]


@app.post("/workflow-subscriptions")
def create_workflow_subscription(subscription: WorkflowEventSubscription) -> dict:
    try:
        return workflow_subscription.subscribe(subscription).model_dump(mode="json")
    except WorkflowSubscriptionError as error:
        raise map_domain_error(error) from error


@app.get("/skill-runtime/executions")
def list_skill_runtime_executions() -> list[dict]:
    return [item.model_dump(mode="json") for item in skill_runtime.list_executions()]


@app.get("/skill-runtime/failures")
def list_skill_runtime_failures() -> list[dict]:
    return [item.model_dump(mode="json") for item in skill_runtime.list_failures()]


@app.get("/telemetry/interactions/{interaction_id}")
def get_telemetry_interaction(interaction_id: str) -> dict:
    item = telemetry_service.get_interaction(interaction_id)
    if item is None:
        raise HTTPException(status_code=404, detail="telemetry interaction not found")
    return item.model_dump(mode="json")


@app.get("/telemetry/interactions/{interaction_id}/steps")
def list_telemetry_steps(interaction_id: str) -> list[dict]:
    return [item.model_dump(mode="json") for item in telemetry_service.list_steps(interaction_id)]


@app.get("/telemetry/feedback")
def list_telemetry_feedback(scope_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in telemetry_service.list_feedback(scope_id=scope_id)]


@app.get("/telemetry/version-bindings/{interaction_id}")
def get_version_binding(interaction_id: str) -> dict:
    item = telemetry_service.get_version_binding(interaction_id)
    if item is None:
        raise HTTPException(status_code=404, detail="version binding not found")
    return item.model_dump(mode="json")


@app.get("/telemetry/policies")
def list_collection_policies() -> list[dict]:
    return [item.model_dump(mode="json") for item in collection_policy_service.list_policies()]


@app.get("/evaluation/candidates")
def list_candidate_evaluations() -> list[dict]:
    return [item.model_dump(mode="json") for item in evaluation_summary_service.list_records()]


@app.get("/evaluation/candidates/{candidate_id}")
def get_candidate_evaluation(candidate_id: str) -> dict:
    item = evaluation_summary_service.get(candidate_id)
    if item is None:
        raise HTTPException(status_code=404, detail="candidate evaluation not found")
    return item.model_dump(mode="json")


@app.get("/upgrade-logs/{stream}/{day}")
def list_upgrade_log_events(stream: str, day: str) -> list[dict]:
    return [item.model_dump(mode="json") for item in upgrade_log_service.read_events(stream, day)]


@app.get("/core-skills/replay/failed-interactions")
def list_failed_replay_candidates() -> dict:
    return {"interaction_ids": core_replay_selector.select_failed_interactions()}


@app.get("/core-skills/cost/{app_id}")
def summarize_app_cost(app_id: str) -> dict:
    return core_cost_analyzer.summarize_app_cost(app_id)


@app.get("/core-skills/acceptance/{candidate_id}")
def get_acceptance_report(candidate_id: str) -> dict:
    return core_acceptance_report.build_report(candidate_id)


@app.get("/core-skills/archive/{candidate_id}")
def get_archive_summary(candidate_id: str) -> dict:
    item = evaluation_summary_service.get(candidate_id)
    if item is None:
        raise HTTPException(status_code=404, detail="candidate evaluation not found")
    return core_archive_summary.summarize_evaluation(item)


@app.post("/practice/review")
def review_practice(request: PracticeReviewRequest) -> dict:
    try:
        return practice_review.review(request).model_dump(mode="json")
    except PracticeReviewError as error:
        raise map_domain_error(error) from error


@app.post("/skills/suggest-from-experience")
def suggest_skill_from_experience(request: SkillSuggestionRequest) -> dict:
    try:
        return skill_suggestion.suggest(request).model_dump(mode="json")
    except SkillSuggestionError as error:
        raise map_domain_error(error) from error


@app.post("/self-refinement/propose")
def propose_self_refinement(request: SelfRefinementRequest) -> dict:
    try:
        result = self_refinement.propose(request)
        proposal_review.register_proposals(result)
        return result.model_dump(mode="json")
    except SelfRefinementError as error:
        raise map_domain_error(error) from error


@app.get("/self-refinement/proposals")
def list_self_refinement_proposals(app_instance_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in proposal_review.list_proposals(app_instance_id)]


@app.get("/self-refinement/reviews")
def list_self_refinement_reviews() -> list[dict]:
    return [item.model_dump(mode="json") for item in proposal_review.list_reviews()]


@app.post("/self-refinement/review")
def review_self_refinement_proposal(request: ProposalReviewRequest) -> dict:
    try:
        return proposal_review.review(request).model_dump(mode="json")
    except ProposalReviewError as error:
        raise map_domain_error(error) from error


@app.post("/self-refinement/analyze-priority")
def analyze_self_refinement_priority(request: PriorityAnalysisRequest) -> dict:
    try:
        return priority_analysis.analyze(request).model_dump(mode="json")
    except PriorityAnalysisError as error:
        raise map_domain_error(error) from error


@app.post("/self-refinement/loop")
def run_self_refinement_loop(request: RefinementLoopRequest) -> dict:
    try:
        return refinement_loop.run(request).model_dump(mode="json")
    except (PriorityAnalysisError, ProposalReviewError, ValueError) as error:
        raise map_domain_error(error) from error


@app.get("/self-refinement/hypotheses")
def list_refinement_hypotheses(app_instance_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in refinement_memory.list_hypotheses(app_instance_id)]


@app.get("/self-refinement/experiments")
def list_refinement_experiments(hypothesis_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in refinement_memory.list_experiments(hypothesis_id)]


@app.get("/self-refinement/verifications")
def list_refinement_verifications(hypothesis_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in refinement_memory.list_verifications(hypothesis_id)]


@app.get("/self-refinement/decisions")
def list_refinement_decisions(hypothesis_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in refinement_memory.list_decisions(hypothesis_id)]


@app.get("/self-refinement/rollout-queue")
def list_refinement_rollout_queue(app_instance_id: str | None = None, hypothesis_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in refinement_memory.list_queue(app_instance_id, hypothesis_id)]


@app.get("/self-refinement/overview")
def get_refinement_overview(app_instance_id: str) -> dict:
    return refinement_memory.build_overview(app_instance_id).model_dump(mode="json")


@app.get("/self-refinement/dashboard")
def get_refinement_dashboard(app_instance_id: str, limit: int = 5) -> dict:
    return refinement_memory.build_dashboard(app_instance_id, limit=limit).model_dump(mode="json")


@app.get("/self-refinement/failed-hypotheses")
def list_failed_hypotheses(app_instance_id: str | None = None, hypothesis_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in refinement_memory.list_failed_hypotheses(app_instance_id, hypothesis_id)]


@app.get("/self-refinement/rollout-queue-page")
def get_refinement_rollout_queue_page(
    app_instance_id: str | None = None,
    hypothesis_id: str | None = None,
    proposal_id: str | None = None,
    status: str | None = None,
    limit: int | None = None,
) -> dict:
    return refinement_memory.list_queue_page(
        build_refinement_filter(
            app_instance_id=app_instance_id,
            hypothesis_id=hypothesis_id,
            proposal_id=proposal_id,
            status=status,
            limit=limit,
        )
    ).model_dump(mode="json")


@app.get("/self-refinement/failed-hypotheses-page")
def get_failed_hypotheses_page(
    app_instance_id: str | None = None,
    hypothesis_id: str | None = None,
    proposal_id: str | None = None,
    limit: int | None = None,
) -> dict:
    return refinement_memory.list_failed_hypothesis_page(
        build_refinement_filter(
            app_instance_id=app_instance_id,
            hypothesis_id=hypothesis_id,
            proposal_id=proposal_id,
            limit=limit,
        )
    ).model_dump(mode="json")


@app.get("/self-refinement/stats")
def get_refinement_stats(
    app_instance_id: str | None = None,
    hypothesis_id: str | None = None,
    proposal_id: str | None = None,
    verification_outcome: str | None = None,
) -> dict:
    return refinement_memory.get_stats_summary(
        build_refinement_filter(
            app_instance_id=app_instance_id,
            hypothesis_id=hypothesis_id,
            proposal_id=proposal_id,
            verification_outcome=verification_outcome,
        )
    ).model_dump(mode="json")


@app.get("/self-refinement/governance-dashboard")
def get_refinement_governance_dashboard(
    app_instance_id: str | None = None,
    hypothesis_id: str | None = None,
    proposal_id: str | None = None,
    status: str | None = None,
    verification_outcome: str | None = None,
    recent_limit: int = 5,
) -> dict:
    return refinement_memory.get_governance_dashboard(
        build_refinement_filter(
            app_instance_id=app_instance_id,
            hypothesis_id=hypothesis_id,
            proposal_id=proposal_id,
            status=status,
            verification_outcome=verification_outcome,
        ),
        recent_limit=recent_limit,
    ).model_dump(mode="json")


@app.get("/self-refinement/operator-summary")
def get_refinement_operator_summary(app_instance_id: str, recent_limit: int = 5) -> dict:
    try:
        priority = priority_analysis.analyze(PriorityAnalysisRequest(app_instance_id=app_instance_id))
    except PriorityAnalysisError:
        priority = None
    return refinement_memory.build_operator_summary(
        app_instance_id=app_instance_id,
        proposals=proposal_review.list_proposals(app_instance_id),
        reviews=proposal_review.list_reviews(),
        priority=priority,
        recent_limit=recent_limit,
    ).model_dump(mode="json")


@app.post("/self-refinement/rollout-queue/{queue_id}/{action}")
def transition_refinement_rollout_queue(queue_id: str, action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    try:
        return refinement_rollout.transition(
            queue_id=queue_id,
            action=action,
            reviewer=payload.get("reviewer", "system"),
            note=payload.get("note", ""),
        ).model_dump(mode="json")
    except (ValueError, ProposalReviewError) as error:
        raise map_domain_error(error) from error


@app.get("/schedules")
def list_schedules(app_instance_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in scheduler.list_schedules(app_instance_id)]


@app.post("/schedules")
def create_schedule(record: ScheduleRecord) -> dict:
    try:
        return scheduler.register_schedule(record).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SchedulerError) as error:
        raise map_domain_error(error) from error


@app.post("/schedules/trigger/interval")
def trigger_interval_schedules(payload: dict | None = None) -> list[dict]:
    app_instance_id = None if payload is None else payload.get("app_instance_id")
    try:
        return [item.model_dump(mode="json") for item in scheduler.trigger_interval_schedules(app_instance_id)]
    except (LifecycleError, RuntimeHostError, SchedulerError) as error:
        raise map_domain_error(error) from error


@app.post("/schedules/trigger/event")
def trigger_event_schedules(payload: dict[str, str]) -> list[dict]:
    try:
        return [
            item.model_dump(mode="json")
            for item in scheduler.emit_event(
                payload["event_name"],
                payload.get("app_instance_id"),
            )
        ]
    except (LifecycleError, RuntimeHostError, SchedulerError) as error:
        raise map_domain_error(error) from error


@app.post("/schedules/{schedule_id}/pause")
def pause_schedule(schedule_id: str) -> dict:
    try:
        return scheduler.pause_schedule(schedule_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SchedulerError) as error:
        raise map_domain_error(error) from error


@app.post("/schedules/{schedule_id}/resume")
def resume_schedule(schedule_id: str) -> dict:
    try:
        return scheduler.resume_schedule(schedule_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SchedulerError) as error:
        raise map_domain_error(error) from error


@app.post("/schedules/{schedule_id}/disable")
def disable_schedule(schedule_id: str) -> dict:
    try:
        return scheduler.disable_schedule(schedule_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SchedulerError) as error:
        raise map_domain_error(error) from error


@app.post("/supervision/policies")
def create_supervision_policy(policy: SupervisionPolicy) -> dict:
    try:
        return supervisor.register_policy(policy).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SupervisorError) as error:
        raise map_domain_error(error) from error


@app.get("/supervision/{app_instance_id}")
def get_supervision_status(app_instance_id: str) -> dict:
    try:
        return supervisor.get_status(app_instance_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SupervisorError) as error:
        raise map_domain_error(error) from error


@app.post("/supervision/{app_instance_id}/observe-failure")
def observe_failure(app_instance_id: str, payload: dict | None = None) -> dict:
    reason = "" if payload is None else payload.get("reason", "")
    try:
        return supervisor.observe_failure(app_instance_id, reason=reason).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SupervisorError) as error:
        raise map_domain_error(error) from error


@app.post("/supervision/{app_instance_id}/attempt-restart")
def attempt_restart(app_instance_id: str) -> dict:
    try:
        return supervisor.attempt_restart(app_instance_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SupervisorError) as error:
        raise map_domain_error(error) from error


@app.post("/supervision/{app_instance_id}/reset")
def reset_supervision(app_instance_id: str) -> dict:
    try:
        return supervisor.reset(app_instance_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SupervisorError) as error:
        raise map_domain_error(error) from error
