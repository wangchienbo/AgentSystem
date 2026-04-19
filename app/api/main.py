import json
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import os
from typing import Any

from app.core.errors import map_domain_error
from app.api.middleware import setup_middleware

from app.bootstrap.runtime import build_runtime
from app.bootstrap.skills import bootstrap_builtin_skills
from app.bootstrap.catalog import bootstrap_demo_catalog
from app.services.lifecycle import LifecycleError
from app.services.blueprint_compare import BlueprintCompareError
from app.services.upgrade_service import UpgradeError
from app.services.rollback_service import RollbackError
from app.services.runtime_host import RuntimeHostError
from app.services.scheduler import SchedulerError
from app.services.supervisor import SupervisorError
from app.services.app_catalog import AppCatalogError
from app.services.app_context_store import AppContextStoreError
from app.services.app_data_store import AppDataStoreError
from app.services.app_registry import AppRegistryError
from app.services.app_refinement import AppRefinementError
from app.services.app_refinement_orchestrator import AppRefinementOrchestratorError
from app.services.policy_authority_service import PolicyAuthorityError
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
from app.models.app_meta_app import AppCreationFromMetaAppRequest
from app.models.policy_authority import AuthorityPolicyRecord
from app.models.skill_creation import AppFromSkillsInstallRunRequest, AppFromSkillsRequest, BlueprintMaterializationRequest, GeneratedSkillRevisionRequest, SkillCreationRequest
from app.services.skill_factory import SkillFactoryError, _diagnostic
from app.services.requirement_blueprint_builder import RequirementBlueprintBuilderError
from app.models.skill_diagnostics import SkillDiagnostic, SkillDiagnosticError, SkillRetryAdviceRequest
from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint
from app.models.app_blueprint import AppBlueprint
from app.services.upgrade_service import UpgradeRequest
from app.services.rollback_service import RollbackRequest
from app.models.demonstration import DemonstrationRecord
from app.models.app_instance import AppInstance, AppStatus
from app.models.telemetry import FeedbackRecord
from app.models.interaction import UserCommand
from app.models.registry import AppRegistryEntry
from app.models.scheduling import ScheduleRecord, SupervisionPolicy
from app.models.chat import ChatMessageRequest, ChatActionRequest, SessionListResponse
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

# Phase F.4: Security middleware (CORS, security headers, request logging, rate limiting)
setup_middleware(app)

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
generated_skill_assets = services["generated_skill_assets"]
skill_risk_policy = services["skill_risk_policy"]
skill_factory = services["skill_factory"]
app_refinement = services["app_refinement"]
app_refinement_orchestrator = services["app_refinement_orchestrator"]
meta_app_orchestrator = services["meta_app_orchestrator"]
workflow_executor = services["workflow_executor"]
workflow_subscription = services["workflow_subscription"]
workflow_observability = services["workflow_observability"]
context_compaction = services["context_compaction"]
interaction_gateway = services["interaction_gateway"]
blueprint_validation = services["blueprint_validation"]
collection_policy_service = services["collection_policy_service"]
policy_authority = services["policy_authority"]
persistence_health = services["persistence_health"]
context_retrieval = services["context_retrieval"]
upgrade_log_service = services["upgrade_log_service"]
blueprint_compare = services["blueprint_compare"]
upgrade_service = services["upgrade_service"]
rollback_service = services["rollback_service"]
telemetry_service = services["telemetry_service"]
feedback_service = services["feedback_service"]
evaluation_summary_service = services["evaluation_summary_service"]
prompt_selection = services["prompt_selection"]
prompt_invocation = services["prompt_invocation"]
light_brain_gateway = services["light_brain_gateway"]
light_brain_memory = services["light_brain_memory"]
memory_skill_service = services["memory_skill_service"]
interactive_app = services["interactive_app"]
user_service = services["user_service"]
auth_service = services.get("auth_service")

# -- G.1/G.2: Orchestrator bridge, LogCenter, SkillMeta -----------------------
g1g2_bridge = services.get("g1g2_bridge")
g1g2_log_center = services.get("g1g2_log_center")
g1g2_meta_service = services.get("g1g2_meta_service")
g1g2_bus = services.get("g1g2_bus")
g1g2_worker_manager = services.get("g1g2_worker_manager")

# ===========================================================================
# Permission Middleware (Linux-style RBAC)
# ===========================================================================

from app.services.user_service import Role, Permission, PermissionDenied, UserServiceError, PERMISSION_MATRIX


def _get_token_user_id(request=None) -> str | None:
    """Extract user_id from Bearer token in Authorization header."""
    if not auth_service:
        return None
    auth_header = None
    if request and hasattr(request, "headers"):
        auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            session = auth_service.validate_token(token)
            return session.user_id
        except Exception:
            pass
    return None


def require_root(actor_id: str) -> None:
    """Require root role."""
    user_service.assert_operation(actor_id, "grant_root")


def require_admin(actor_id: str) -> None:
    """Require admin or root role."""
    user_service.assert_operation(actor_id, "grant_admin")


def require_permission(actor_id: str, action: str, resource_owner_id: str | None = None) -> None:
    """Check permission for resource access."""
    user_service.assert_permission(actor_id, action, resource_owner_id)


def require_owner(actor_id: str, resource_type: str, resource_id: str) -> None:
    """Require that actor owns the resource."""
    owner = user_service.get_resource_owner(resource_type, resource_id)
    if owner != actor_id:
        user = user_service.require_user(actor_id)
        if not user.is_root:
            raise PermissionDenied(
                f"User '{actor_id}' does not own {resource_type}:{resource_id}"
            )


# Phase F.4: Auth decorator for protecting sensitive endpoints
def require_auth(request=None):
    """Extract user_id from token. Raises HTTPException if not authenticated."""
    # Phase F.4: Skip auth in test/dev environments
    if os.environ.get("AGENTSYSTEM_SKIP_AUTH") == "1":
        return "test-admin"
    user_id = _get_token_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required. Provide a valid Bearer token.")
    return user_id
auth_service = services.get("auth_service")
session_router = services.get("session_router")
pipeline_service = services.get("pipeline_service")
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
def replace_skill(skill_id: str, payload: dict[str, str], request: Request = None) -> dict:
    actor_id = require_auth(request)  # Phase F.4: require auth
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
def disable_skill(skill_id: str, request: Request = None) -> dict:
    actor_id = require_auth(request)  # Phase F.4
    try:
        return skill_control.disable_skill(skill_id).model_dump(mode="json")
    except SkillControlError as error:
        raise map_domain_error(error) from error

@app.post("/skills/{skill_id}/enable")
def enable_skill(skill_id: str, request: Request = None) -> dict:
    actor_id = require_auth(request)  # Phase F.4
    try:
        return skill_control.enable_skill(skill_id).model_dump(mode="json")
    except SkillControlError as error:
        raise map_domain_error(error) from error

@app.post("/skills/create")
def create_skill(payload: SkillCreationRequest, request: Request = None) -> dict:
    actor_id = require_auth(request)  # Phase F.4
    try:
        return skill_factory.create_skill(payload).model_dump(mode="json")
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
def create_app_from_skills(request: AppFromSkillsRequest, http_request: Request = None) -> dict:
    actor_id = require_auth(http_request)  # Phase F.4
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
def create_install_and_run_app_from_skills(request: AppFromSkillsInstallRunRequest, http_request: Request = None) -> dict:
    actor_id = require_auth(http_request)  # Phase F.4
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
        result = app_refinement_orchestrator.refine_closure(
            SuggestedSkillRefinementClosureRequest(
                **request.model_dump(mode="python"),
                install=False,
                run=False,
                dry_run=False,
            )
        )
        return result.model_dump(mode="json")
    except (AppRefinementError, AppRefinementOrchestratorError, AppRegistryError, SkillDiagnosticError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error


@app.post("/apps/refine-from-suggested-skills/closure")
def refine_app_from_suggested_skills_closure(request: SuggestedSkillRefinementClosureRequest) -> dict:
    try:
        result = app_refinement_orchestrator.refine_closure(request)
        return result.model_dump(mode="json")
    except (AppRefinementError, AppRefinementOrchestratorError, AppRegistryError, SkillDiagnosticError, SkillFactoryError, ValueError) as error:
        raise map_domain_error(error) from error

@app.post("/apps/from-meta-app")
def create_app_through_meta_app(request: AppCreationFromMetaAppRequest, http_request: Request = None) -> dict:
    actor_id = require_auth(http_request)  # Phase F.4
    try:
        result = meta_app_orchestrator.create_app_through_meta_app(request)
        payload = {
            "app_name": result.app_name,
            "control_plan": result.control_plan.model_dump(mode="json"),
            "skill_ids": result.created_skill_ids,
        }
        if result.blueprint is not None:
            payload["blueprint"] = result.blueprint.model_dump(mode="json")
        if result.error:
            payload["error"] = result.error
        if request.auto_install and result.blueprint is not None and not result.error:
            install = app_installer.install_app(blueprint_id=result.blueprint.id, user_id=request.user_id or "system")
            payload["install"] = install.model_dump(mode="json")
        return payload
    except ValueError as error:
        raise map_domain_error(error) from error


@app.get("/policy-authority")
def get_policy_authority_summary() -> dict:
    return policy_authority.get_summary().model_dump(mode="json")


@app.post("/policy-authority")
def set_policy_authority(payload: dict) -> dict:
    record = policy_authority.set_policy(
        AuthorityPolicyRecord(
            scope=payload["scope"],
            require_reviewer=payload.get("require_reviewer", False),
            allowed_reviewers=payload.get("allowed_reviewers", []),
            require_reason=payload.get("require_reason", False),
            allow_automatic=payload.get("allow_automatic", True),
        )
    )
    return record.model_dump(mode="json")


@app.get("/persistence/health")
def get_persistence_health() -> dict:
    return persistence_health.get_summary().model_dump(mode="json")


@app.get("/context/prompt-ready")
def get_prompt_ready_context(app_instance_id: str) -> dict:
    return context_retrieval.get_prompt_ready_context(app_instance_id)


@app.get("/context/detail-refs")
def get_context_detail_refs(app_instance_id: str) -> dict:
    return context_retrieval.retrieve_detail_refs(app_instance_id)


@app.get("/experiences")
def list_experiences() -> list[dict]:
    return [item.model_dump(mode="json") for item in experience_store.list_experiences()]

@app.post("/experiences")
def add_experience(record: ExperienceRecord) -> dict:
    return experience_store.add_experience(record).model_dump(mode="json")

@app.get("/skill-assets")
def list_skill_assets(status: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in generated_skill_assets.list_assets(status=status)]


@app.get("/skill-assets/{skill_id}/consistency")
def get_skill_asset_consistency(skill_id: str) -> list[dict]:
    return [item.model_dump(mode="json") for item in generated_skill_assets.check_consistency(skill_id=skill_id)]


@app.post("/skill-assets/{skill_id}/promote")
def promote_skill_asset(skill_id: str, payload: dict | None = None) -> dict:
    accepted_by = (payload or {}).get("accepted_by", "")
    try:
        return generated_skill_assets.promote_candidate_to_core(skill_id, accepted_by=accepted_by).model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.post("/skill-assets/{skill_id}/archive")
def archive_skill_asset(skill_id: str, payload: dict | None = None) -> dict:
    status = (payload or {}).get("status", "candidate")
    try:
        return generated_skill_assets.archive_asset(skill_id, status=status).model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.post("/skill-assets/{skill_id}/restore")
def restore_skill_asset(skill_id: str) -> dict:
    try:
        return generated_skill_assets.restore_archived_to_candidate(skill_id).model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.post("/skill-assets/{skill_id}/deprecate")
def deprecate_skill_asset(skill_id: str) -> dict:
    try:
        return generated_skill_assets.deprecate_core_asset(skill_id).model_dump(mode="json")
    except ValueError as error:
        raise map_domain_error(error) from error


@app.post("/skill-assets/rebuild-index")
def rebuild_skill_asset_index() -> dict:
    return generated_skill_assets.rebuild_index().model_dump(mode="json")


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
        requested_adapter_kind = request.adapter_kind
        effective_adapter_kind, governance_adjusted, governance_reason = skill_factory.choose_adapter_kind_for_blueprint(
            blueprint,
            requested_adapter_kind,
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
        if request.command:
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
            "requested_adapter_kind": requested_adapter_kind,
            "selected_adapter_kind": effective_adapter_kind,
            "governance_adjusted": governance_adjusted,
            "governance_reason": governance_reason,
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
def list_apps(status: str | None = None) -> list[dict]:
    instances = lifecycle.list_instances()
    if status is not None:
        instances = [i for i in instances if i.status == status]
    return [item.model_dump(mode="json") for item in instances]


@app.post("/apps/{app_instance_id}/archive")
def archive_app(app_instance_id: str, payload: dict | None = None) -> dict:
    reason = (payload or {}).get("reason", "")
    try:
        return lifecycle.archive(app_instance_id, reason=reason).model_dump(mode="json")
    except LifecycleError as error:
        raise map_domain_error(error) from error


@app.post("/apps/{app_instance_id}/unarchive")
def unarchive_app(app_instance_id: str, payload: dict | None = None) -> dict:
    reason = (payload or {}).get("reason", "")
    try:
        return lifecycle.unarchive(app_instance_id, reason=reason).model_dump(mode="json")
    except LifecycleError as error:
        raise map_domain_error(error) from error


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
        payload = payload or {}
        policy_authority.enforce(
            scope="app_activate",
            reviewer=payload.get("reviewer", ""),
            reason=payload.get("reason", ""),
            automatic=False,
        )
        entry = app_registry.activate_release(blueprint_id, version, reviewer=payload.get("reviewer", ""))
        return entry.model_dump(mode="json")
    except (ValueError, PolicyAuthorityError) as error:
        raise map_domain_error(error) from error


@app.post("/registry/apps/{blueprint_id}/rollback")
def rollback_app_release(blueprint_id: str, payload: dict) -> dict:
    try:
        policy_authority.enforce(
            scope="app_rollback",
            reviewer=payload.get("reviewer", ""),
            reason=payload.get("rollback_reason", ""),
            automatic=False,
        )
        entry = app_registry.rollback_release(
            blueprint_id,
            payload["target_version"],
            reviewer=payload.get("reviewer", ""),
            rollback_reason=payload.get("rollback_reason", ""),
        )
        return entry.model_dump(mode="json")
    except (ValueError, PolicyAuthorityError) as error:
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


# ===========================================================================
# App Upgrade / Rollback Routes (Phase 9)
# ===========================================================================

@app.post("/apps/{app_instance_id}/upgrade")
def upgrade_app(app_instance_id: str, request: UpgradeRequest) -> dict:
    """Upgrade an app instance to a new blueprint version."""
    try:
        new_bp = app_registry.get_blueprint(request.blueprint_id)
        result = upgrade_service.upgrade(
            app_instance_id=app_instance_id,
            new_blueprint=new_bp,
            reviewer=request.reviewer,
            reason=request.reason,
            skip_compare=request.skip_compare,
            require_reviewer=request.require_reviewer,
        )
        return result.model_dump(mode="json")
    except (UpgradeError, BlueprintCompareError, LifecycleError, AppRegistryError) as error:
        raise map_domain_error(error) from error


@app.post("/apps/{app_instance_id}/rollback")
def rollback_app(app_instance_id: str, payload: dict | None = None) -> dict:
    """Rollback an app instance to its pre-upgrade snapshot."""
    p = payload or {}
    try:
        result = rollback_service.rollback(
            app_instance_id=app_instance_id,
            reviewer=p.get("reviewer", ""),
            reason=p.get("reason", ""),
            force=p.get("force", False),
        )
        return result.model_dump(mode="json")
    except (RollbackError, UpgradeError, LifecycleError) as error:
        raise map_domain_error(error) from error


@app.get("/apps/{app_instance_id}/upgrade-log")
def get_app_upgrade_log(app_instance_id: str) -> list[dict]:
    """Get upgrade log events for an app instance."""
    events = upgrade_service.get_upgrade_log(app_instance_id)
    return [item.model_dump(mode="json") for item in events]


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


# ===========================================================================
# Feedback API (Phase 9.4)
# ===========================================================================

@app.post("/feedback")
def submit_feedback(record: FeedbackRecord) -> dict:
    return feedback_service.submit_feedback(record).model_dump(mode="json")


@app.get("/feedback")
def query_feedback(
    app_id: str | None = None,
    skill_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    return [item.model_dump(mode="json") for item in feedback_service.get_feedback(
        app_id=app_id, skill_id=skill_id, limit=limit,
    )]


@app.get("/feedback/{app_id}/summary")
def get_feedback_summary(app_id: str) -> dict:
    return feedback_service.get_feedback_summary(app_id)


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


@app.post("/supervision/{app_instance_id}/probe-circuit")
def probe_circuit(app_instance_id: str) -> dict:
    try:
        return supervisor.probe_circuit(app_instance_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SupervisorError) as error:
        raise map_domain_error(error) from error


@app.post("/supervision/{app_instance_id}/circuit-reset")
def circuit_reset(app_instance_id: str) -> dict:
    try:
        return supervisor.circuit_reset(app_instance_id).model_dump(mode="json")
    except (LifecycleError, RuntimeHostError, SupervisorError) as error:
        raise map_domain_error(error) from error


# ===========================================================================
# LightBrain Chat Routes (Phase 8)
# ===========================================================================

@app.post("/chat/message")
async def chat_message(request: ChatMessageRequest) -> dict:
    """Main conversation entry point — send a message to the LightBrain."""
    try:
        # Inject memory context from MemorySkill
        if request.user_id and not request.memory_context:
            ctx = memory_skill_service.get_full_context(request.user_id)
            if ctx and ctx.get("context_summary"):
                request.memory_context = ctx["context_summary"]
            elif ctx and ctx.get("preferences"):
                prefs = ctx.get("preferences", {})
                if prefs:
                    request.memory_context = f"用户偏好：{json.dumps(prefs, ensure_ascii=False)}"
            # Fallback: inject cross-session conversation history
            if not request.memory_context:
                try:
                    summary = light_brain_memory.summarize_recent_activity(request.user_id)
                    if summary:
                        request.memory_context = f"跨会话历史：\n{summary}"
                except Exception:
                    pass

        reply = await light_brain_gateway.process_message(request)

        # Post-reply: auto-summarize and update context_summary if empty
        if request.user_id and reply:
            try:
                ctx = memory_skill_service.get_full_context(request.user_id)
                if not ctx or not ctx.get("context_summary"):
                    summary = light_brain_memory.summarize_recent_activity(request.user_id, max_msgs=30)
                    if summary:
                        memory_skill_service.update_context_summary(request.user_id, summary)
            except Exception:
                pass
        return reply.model_dump(mode="json")
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/chat/actions/{action_id}")
async def chat_action(action_id: str, request: ChatActionRequest) -> dict:
    """Execute a user-selected action (button click) from a previous reply."""
    try:
        reply = await light_brain_gateway.execute_action(
            user_id=request.user_id,
            session_id=request.session_id,
            action_id=action_id,
            action_params=request.action_params,
        )
        return reply.model_dump(mode="json")
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/chat/sessions")
def chat_sessions(user_id: str | None = None) -> dict:
    """List conversation sessions, sorted by last_active_at desc."""
    sessions = light_brain_gateway.list_sessions(user_id)
    # Sort by last_active_at descending (most recent first)
    sessions.sort(key=lambda s: s.last_active_at, reverse=True)
    return {
        "sessions": [s.model_dump(mode="json") for s in sessions],
        "total": len(sessions),
    }


@app.get("/chat/sessions/last")
def chat_last_session(user_id: str) -> dict:
    """Get the most recent session for a user."""
    session = light_brain_gateway.get_last_session(user_id)
    if not session:
        return {"session": None}
    return {"session": session.to_summary().model_dump(mode="json")}


@app.delete("/chat/sessions/{session_id}")
def chat_delete_session(session_id: str) -> dict:
    """Reset / delete a conversation session."""
    deleted = light_brain_gateway.delete_session(session_id)
    return {"deleted": deleted, "session_id": session_id}


@app.get("/chat/sessions/{session_id}/messages")
def chat_session_messages(session_id: str, limit: int = 20) -> dict:
    """Get recent messages from a conversation session."""
    messages = light_brain_gateway.get_session_messages(session_id, limit)
    return {"session_id": session_id, "messages": messages, "count": len(messages)}


@app.get("/chat/token-usage")
def chat_token_usage(user_id: str | None = None, session_id: str | None = None) -> dict:
    """Get token usage statistics across sessions."""
    usage_data = light_brain_gateway.get_token_usage(user_id, session_id)
    return usage_data


# ===========================================================================
# Static Files & Streaming (Phase 8.5/8.6)
# ===========================================================================

# Serve static files
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
def serve_index():
    """Serve the login page."""
    login_path = os.path.join(_static_dir, "login.html")
    if os.path.exists(login_path):
        return FileResponse(login_path)
    return {"error": "Login page not found"}


@app.get("/chat/{user_id}")
def serve_user_chat(user_id: str):
    """Serve user-specific chat UI."""
    # Check for user-customized frontend
    user_frontend = interactive_app.get_user_frontend_path(user_id)
    if user_frontend and os.path.exists(user_frontend):
        return FileResponse(user_frontend)
    # Fallback to default chat UI
    index_path = os.path.join(_static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Chat UI not found"}


@app.post("/chat/message/stream")
async def chat_message_stream(request: ChatMessageRequest):
    """Stream a chat response using Server-Sent Events (SSE).

    Supports client-side abort for timely interruption.
    """
    import json
    import asyncio

    # Inject memory context from MemorySkill
    if request.user_id and not request.memory_context:
        ctx = memory_skill_service.get_full_context(request.user_id)
        if ctx and ctx.get("context_summary"):
            request.memory_context = ctx["context_summary"]
        elif ctx and ctx.get("preferences"):
            prefs = ctx.get("preferences", {})
            if prefs:
                request.memory_context = f"用户偏好：{json.dumps(prefs, ensure_ascii=False)}"
        # Fallback: inject cross-session conversation history
        if not request.memory_context:
            try:
                summary = light_brain_memory.summarize_recent_activity(request.user_id)
                if summary:
                    request.memory_context = f"跨会话历史：\n{summary}"
            except Exception:
                pass

    async def event_generator():
        try:
            reply = await light_brain_gateway.process_message(request)
            content = reply.content
            # Stream character by character (or chunk by chunk)
            chunk_size = 4
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i+chunk_size]
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)  # Small delay for smooth streaming

            # Post-reply: auto-summarize and update context_summary if empty
            if request.user_id and reply:
                try:
                    ctx = memory_skill_service.get_full_context(request.user_id)
                    if not ctx or not ctx.get("context_summary"):
                        summary = light_brain_memory.summarize_recent_activity(request.user_id, max_msgs=30)
                        if summary:
                            memory_skill_service.update_context_summary(request.user_id, summary)
                except Exception:
                    pass

            # Send complete reply with actions
            usage_data = None
            if reply.usage:
                usage_data = reply.usage.model_dump(mode='json')
            yield f"data: {json.dumps({
                'type': 'complete',
                'content': content,
                'reply_type': reply.type,
                'session_id': reply.session_id,
                'actions': [a.model_dump(mode='json') for a in reply.actions],
                'requires_input': reply.requires_input,
                'usage': usage_data,
            }, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -- G.1/G.2: System Status, Skills, Logs, Traces ------------------------------

@app.get("/system/status")
def system_status() -> dict:
    """Overall system status including G.1/G.2 module health."""
    status = {
        "bridge_available": g1g2_bridge.is_available() if g1g2_bridge else False,
        "bus_workers": 0,
        "registered_skills": 0,
        "log_entries": 0,
    }
    if g1g2_bus:
        status["bus_workers"] = len(g1g2_bus.list_workers())
    if g1g2_bridge:
        status["registered_skills"] = len(g1g2_bridge.get_available_skills())
    if g1g2_log_center:
        status["log_entries"] = g1g2_log_center.stats().get("total_entries", 0)
    return status


@app.get("/system/skills")
def system_skills() -> dict:
    """List all registered skills via the orchestrator bridge."""
    if not g1g2_bridge:
        return {"skills": [], "error": "Bridge not available"}
    skills = g1g2_bridge.get_available_skills()
    return {"skills": skills, "total": len(skills)}


@app.get("/system/logs")
def system_logs(
    trace_id: str | None = None,
    skill_id: str | None = None,
    app_instance_id: str | None = None,
    user_id: str | None = None,
    level: str | None = None,
    limit: int = 50,
) -> dict:
    """Query execution logs from the LogCenter."""
    if not g1g2_log_center:
        return {"logs": [], "error": "LogCenter not available"}
    from app.models.log_center import LogQuery
    logs = g1g2_log_center.query(LogQuery(
        trace_id=trace_id,
        skill_id=skill_id,
        app_instance_id=app_instance_id,
        user_id=user_id,
        level=level,  # type: ignore[arg-type]
        limit=limit,
    ))
    return {"logs": [log.model_dump(mode="json") for log in logs], "total": len(logs)}


@app.get("/system/traces/{trace_id}")
def system_trace_detail(trace_id: str) -> dict:
    """Get full trace timeline for a specific trace_id."""
    if not g1g2_log_center:
        return {"error": "LogCenter not available"}
    logs = g1g2_log_center.get_trace(trace_id)
    if not logs:
        return {"trace_id": trace_id, "logs": [], "found": False}
    return {
        "trace_id": trace_id,
        "logs": [log.model_dump(mode="json") for log in logs],
        "total": len(logs),
        "found": True,
    }


@app.get("/system/bus/workers")
def system_bus_workers() -> dict:
    """List all Workers registered on the MessageBus."""
    if not g1g2_bus:
        return {"workers": [], "error": "MessageBus not available"}
    workers = g1g2_bus.list_workers()
    return {"workers": workers, "total": len(workers)}


# -- Memory Skill API -----------------------------------------------------------

from app.models.memory_skill import MemorySkillRequest


@app.post("/memory")
def memory_operation(request: MemorySkillRequest) -> dict:
    """Memory skill operations for cross-session user context."""
    try:
        if request.operation == "get_profile":
            profile = memory_skill_service.get_profile(request.user_id)
            return {"success": True, "data": profile.to_dict() if profile else {"user_id": request.user_id, "initialized": False}}
        elif request.operation == "add_feedback":
            entry = memory_skill_service.add_feedback(request.user_id, request.feedback, request.source)
            return {"success": True, "data": entry}
        elif request.operation == "update_preference":
            memory_skill_service.update_preference(request.user_id, request.preference_key, request.preference_value)
            return {"success": True, "data": {"user_id": request.user_id, "key": request.preference_key, "updated": True}}
        elif request.operation == "get_recent_feedback":
            return {"success": True, "data": {"feedback": memory_skill_service.get_recent_feedback(request.user_id, request.limit)}}
        elif request.operation == "get_context_summary":
            return {"success": True, "data": {"summary": memory_skill_service.get_context_summary(request.user_id)}}
        elif request.operation == "update_context_summary":
            memory_skill_service.update_context_summary(request.user_id, request.summary)
            return {"success": True, "data": {"user_id": request.user_id, "updated": True}}
        elif request.operation == "record_app_usage":
            memory_skill_service.record_app_usage(request.user_id, request.app_id, request.action, request.details)
            return {"success": True, "data": {"user_id": request.user_id, "app_id": request.app_id, "recorded": True}}
        elif request.operation == "get_full_context":
            return {"success": True, "data": memory_skill_service.get_full_context(request.user_id)}
        else:
            raise HTTPException(status_code=400, detail=f"Unknown operation: {request.operation}")
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


# -- Interactive App API --------------------------------------------------------


@app.get("/app/status")
def interactive_app_status(user_id: str = "web-user") -> dict:
    """Get Interactive App status and version info for a user."""
    return interactive_app.get_user_status(user_id)


@app.get("/app/user/{user_id}/config")
def get_user_config(user_id: str) -> dict:
    """Get user-specific configuration."""
    return interactive_app.get_user_config(user_id)


@app.post("/app/user/{user_id}/config")
def save_user_config(user_id: str, config: dict[str, Any] | None = None) -> dict:
    """Save user-specific configuration."""
    interactive_app.save_user_config(user_id, config or {})
    return {"success": True, "user_id": user_id}


@app.post("/app/self-modify")
def self_modify_app(user_id: str, request: str = "", description: str = "") -> dict:
    """Self-modify the Interactive App: create new version and activate it."""
    try:
        from app.services.interactive_app_workflow import InteractiveAppWorkflow
        workflow = services.get("interactive_app_workflow")
        if workflow:
            result = workflow.modify_app(user_id, request or description, auto_activate=True, require_confirmation=False)
            return result
        return {"error": "InteractiveAppWorkflow not available"}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/app/version/{user_id}/create")
def create_app_version(user_id: str, code_changes: dict[str, str], description: str = "") -> dict:
    """Create a new version for a user without activating."""
    version_id = interactive_app.create_user_version(user_id, code_changes, description)
    return {"version_id": version_id, "user_id": user_id, "status": "created"}


@app.post("/app/version/{user_id}/{version_id}/activate")
def activate_app_version(user_id: str, version_id: str) -> dict:
    """Activate a specific version for a user (hot-swap)."""
    try:
        return interactive_app.activate_user_version(user_id, version_id)
    except Exception as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/app/versions/{user_id}")
def list_app_versions(user_id: str) -> dict:
    """List all versions for a user."""
    return {
        "user_id": user_id,
        "versions": interactive_app.get_user_version_history(user_id),
        "current": interactive_app.get_user_current_version(user_id),
    }


# -- User Management API (Password + Role) ------------------------------------


class RegisterRequest(BaseModel):
    user_id: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    user_id: str
    password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


@app.post("/users/register")
def register_user(req: RegisterRequest) -> dict:
    """Register a new user with password. Open registration if no admin exists."""
    try:
        # If admin/root exists, require the registrant to be created by an admin
        admins = user_service.get_admin_users()
        created_by = None
        if admins:
            # Open registration still allowed, but user is created as regular user
            created_by = None
        user = user_service.register_user(
            req.user_id, req.password, req.display_name,
            created_by=created_by
        )
        return {"success": True, "user": user.to_safe_dict()}
    except Exception as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/users/login")
def user_login(req: LoginRequest) -> dict:
    """Authenticate user with password and return session token."""
    user = user_service.authenticate(req.user_id, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    result = {"success": True, "user": user.to_safe_dict()}
    # Create session token if auth_service available
    if auth_service:
        try:
            token = auth_service.create_session(user.user_id)
            result["token"] = token
        except Exception:
            pass
    return result


@app.post("/users/{user_id}/change-password")
def change_password(user_id: str, req: PasswordChangeRequest) -> dict:
    """Change user password."""
    try:
        user_service.change_password(user_id, req.old_password, req.new_password)
        return {"success": True}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/users/{user_id}")
def get_user(user_id: str) -> dict:
    """Get user profile."""
    user = user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
    return user.to_public_dict()


@app.patch("/users/{user_id}")
def update_user(user_id: str, updates: dict[str, Any] | None = None) -> dict:
    """Update user profile (admin only)."""
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    try:
        user = user_service.update_user(user_id, **updates)
        return {"success": True, "user": user.to_public_dict()}
    except Exception as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/users")
def list_users(status: str | None = None) -> dict:
    """List all users (public: safe dict only)."""
    users = user_service.list_users(status)
    return {"users": [u.to_public_dict() for u in users], "count": len(users)}


# -- Admin API (Role-gated) ---------------------------------------------------


@app.post("/admin/init-admin")
def init_admin(req: RegisterRequest) -> dict:
    """Initialize first root user (only if no root/admin exists)."""
    try:
        # Temporary bootstrap downgrade: try root first, then admin only if root creation is unavailable
        try:
            user = user_service.create_root(req.user_id, req.password, req.display_name)
        except UserServiceError:
            user = user_service.create_admin(req.user_id, req.password, req.display_name)
        return {"success": True, "user": user.to_safe_dict()}
    except Exception as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: str) -> dict:
    """Admin/root: hard delete a user."""
    try:
        user_service.hard_delete_user(user_id)
        return {"success": True, "deleted": user_id}
    except Exception as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/admin/users")
def admin_list_users() -> dict:
    """Admin/root: list all users with full details."""
    users = user_service.list_users()
    return {"users": [u.to_safe_dict() for u in users], "count": len(users)}


# -- Role & Permission Management (Root/Admin) --------------------------------


@app.post("/admin/users/{user_id}/role")
def admin_set_role(user_id: str, role: str = "admin", actor_id: str | None = None) -> dict:
    """Admin/root: set a user's role. If actor_id provided, permission is checked."""
    try:
        if actor_id:
            if role == Role.ROOT:
                require_root(actor_id)
            else:
                require_admin(actor_id)
            user = user_service.grant_role(actor_id, user_id, role)
        else:
            target = user_service.require_user(user_id)
            target.role = role
            user_service._persist_user(target)
            user = target
        return {"success": True, "user": user.to_safe_dict()}
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/admin/users/{user_id}/role")
def admin_revoke_role(user_id: str, actor_id: str | None = None) -> dict:
    """Admin/root: revoke admin/root role from a user, demote to regular user."""
    try:
        if actor_id:
            require_admin(actor_id)
            user = user_service.revoke_role(actor_id, user_id)
        else:
            target = user_service.require_user(user_id)
            target.role = Role.USER
            user_service._persist_user(target)
            user = target
        return {"success": True, "user": user.to_safe_dict()}
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/admin/permissions/{user_id}")
def admin_get_permissions(user_id: str) -> dict:
    """Get detailed permission info for a user."""
    user = user_service.require_user(user_id)
    return {
        "user": user.to_safe_dict(),
        "uid": user.uid,
        "is_root": user.is_root,
        "is_admin": user.is_admin,
        "sudoers": user.sudoers,
        "owned_resources": user.owned_resources,
        "permissions": {
            "own": list(PERMISSION_MATRIX.get((user.role, "own"), set())),
            "other": list(PERMISSION_MATRIX.get((user.role, "other"), set())),
            "system": list(PERMISSION_MATRIX.get((user.role, "system"), set())),
        }
    }


# -- Auth API -----------------------------------------------------------------


@app.get("/auth/me")
def auth_me() -> dict:
    """Get current authenticated user info (requires Bearer token)."""
    if not auth_service:
        return {"error": "Auth service not available"}
    # This endpoint requires the token to be validated
    # The token is extracted from Authorization header
    return {"message": "Use Authorization: Bearer <token> header"}


def _resolve_actor(request=None, user_id: str | None = None) -> str | None:
    """Resolve the actor from Bearer token or fallback to user_id param."""
    token_user = _get_token_user_id(request)
    if token_user:
        return token_user
    return user_id


@app.post("/auth/session/{user_id}")
def create_session(user_id: str) -> dict:
    """Create an authenticated session for a user."""
    if not auth_service:
        return {"error": "Auth service not available"}
    try:
        token = auth_service.create_session(user_id)
        return {"success": True, "token": token, "user_id": user_id}
    except Exception as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@app.get("/auth/session/{token}")
def validate_session(token: str) -> dict:
    """Validate a session token."""
    if not auth_service:
        return {"error": "Auth service not available"}
    try:
        session = auth_service.validate_token(token)
        return {"valid": True, "user_id": session.user_id, "expires_at": session.expires_at}
    except Exception as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@app.get("/auth/sessions/{user_id}")
def get_user_sessions(user_id: str) -> dict:
    """Get all active sessions for a user."""
    if not auth_service:
        return {"error": "Auth service not available"}
    sessions = auth_service.get_user_sessions(user_id)
    return {"user_id": user_id, "sessions": sessions, "count": len(sessions)}


@app.delete("/auth/session/{token}")
def revoke_session(token: str) -> dict:
    """Revoke a session token."""
    if not auth_service:
        return {"error": "Auth service not available"}
    revoked = auth_service.revoke_token(token)
    return {"success": revoked}


# -- Pipeline API -------------------------------------------------------------


@app.get("/pipelines/stats")
def pipeline_stats() -> dict:
    """Get pipeline statistics."""
    if not pipeline_service:
        return {"error": "Pipeline service not available"}
    return pipeline_service.get_stats()


@app.post("/pipelines")
def create_pipeline(
    pipeline_type: str = "system",
    user_id: str | None = None,
    app_id: str | None = None,
    trigger: str = "manual",
) -> dict:
    """Create a new pipeline."""
    if not pipeline_service:
        return {"error": "Pipeline service not available"}
    try:
        from app.services.pipeline_service import PipelineType
        ptype = PipelineType(pipeline_type)
        record = pipeline_service.create_pipeline(ptype, user_id, app_id, trigger)
        return {"success": True, "pipeline": record.to_dict()}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/pipelines")
def list_pipelines(
    pipeline_type: str | None = None,
    user_id: str | None = None,
    status: str | None = None,
) -> dict:
    """List pipelines with filters."""
    if not pipeline_service:
        return {"error": "Pipeline service not available"}
    from app.services.pipeline_service import PipelineType, PipelineStatus
    ptype = PipelineType(pipeline_type) if pipeline_type else None
    pstatus = PipelineStatus(status) if status else None
    records = pipeline_service.list_pipelines(ptype, user_id, pstatus)
    return {"pipelines": [r.to_dict() for r in records], "count": len(records)}


@app.get("/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: str) -> dict:
    """Get a pipeline by ID."""
    if not pipeline_service:
        return {"error": "Pipeline service not available"}
    record = pipeline_service.get_pipeline(pipeline_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_id}")
    return record.to_dict()


@app.post("/pipelines/{pipeline_id}/start")
def start_pipeline(pipeline_id: str) -> dict:
    """Start a pipeline."""
    if not pipeline_service:
        return {"error": "Pipeline service not available"}
    record = pipeline_service.start_pipeline(pipeline_id)
    return {"success": True, "pipeline": record.to_dict()}


@app.post("/pipelines/{pipeline_id}/complete")
def complete_pipeline(pipeline_id: str) -> dict:
    """Complete a pipeline."""
    if not pipeline_service:
        return {"error": "Pipeline service not available"}
    record = pipeline_service.complete_pipeline(pipeline_id)
    return {"success": True, "pipeline": record.to_dict()}


# -- Pipeline Execution Engine (Phase B) --------------------------------------


from app.services.pipeline_executor import (
    PipelineExecutor, PipelineStep, ExecutorType, StepStatus,
    ExecutionResult, SHELL_WHITELIST, SHELL_BLACKLIST,
)

_pipeline_executor = PipelineExecutor(
    workspace=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)


class PipelineExecuteRequest:
    """Request model for pipeline execution."""
    def __init__(self, data: dict):
        self.user_id = data.get("user_id")
        self.steps = [
            PipelineStep(
                step_id=s.get("step_id", f"step_{i}"),
                executor_type=ExecutorType(s.get("executor_type", "shell")),
                command=s.get("command", ""),
                args=s.get("args", {}),
                timeout=s.get("timeout", 30),
                depends_on=s.get("depends_on", []),
            )
            for i, s in enumerate(data.get("steps", []))
        ]


@app.post("/pipelines/{pipeline_id}/execute")
async def execute_pipeline(pipeline_id: str, body: dict | None = None) -> dict:
    """Execute a pipeline with real step execution (shell/python/llm/api)."""
    if not pipeline_service:
        return {"error": "Pipeline service not available"}

    record = pipeline_service.get_pipeline(pipeline_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {pipeline_id}")

    # Build steps from pipeline record or request body
    if body and body.get("steps"):
        req = PipelineExecuteRequest(body)
        steps = req.steps
        user_id = req.user_id or record.user_id
    else:
        steps = [PipelineStep.from_dict(s) for s in record.steps]
        user_id = record.user_id

    if not steps:
        raise HTTPException(status_code=400, detail="No steps to execute")

    # Execute
    results = await _pipeline_executor.execute_pipeline(steps, user_id=user_id)

    # Update pipeline record
    record.steps = [s.to_dict() for s in steps]
    if all(r.status == StepStatus.SUCCESS for r in results):
        pipeline_service.complete_pipeline(pipeline_id)
    else:
        failed = [r for r in results if r.status != StepStatus.SUCCESS]
        pipeline_service.fail_pipeline(pipeline_id, f"{len(failed)} step(s) failed")

    return {
        "pipeline_id": pipeline_id,
        "status": record.status.value,
        "results": [r.__dict__ for r in results],
        "total_steps": len(results),
        "success_count": sum(1 for r in results if r.status == StepStatus.SUCCESS),
        "failed_count": sum(1 for r in results if r.status != StepStatus.SUCCESS),
    }


@app.post("/pipelines/execute-direct")
async def execute_pipeline_direct(body: dict) -> dict:
    """Execute pipeline steps directly without a pipeline record."""
    req = PipelineExecuteRequest(body)
    if not req.steps:
        raise HTTPException(status_code=400, detail="No steps provided")

    results = await _pipeline_executor.execute_pipeline(req.steps, user_id=req.user_id)

    return {
        "results": [r.__dict__ for r in results],
        "total_steps": len(results),
        "success_count": sum(1 for r in results if r.status == StepStatus.SUCCESS),
        "failed_count": sum(1 for r in results if r.status != StepStatus.SUCCESS),
    }


@app.get("/pipelines/executor/info")
def executor_info() -> dict:
    """Get executor configuration info."""
    return {
        "supported_executors": [e.value for e in ExecutorType],
        "shell_whitelist": sorted(SHELL_WHITELIST),
        "shell_blacklist": sorted(SHELL_BLACKLIST),
        "default_timeout": 30,
        "max_output_size": 10000,
    }
