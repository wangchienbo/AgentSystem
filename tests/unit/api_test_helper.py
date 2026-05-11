from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import map_domain_error

from app.ai import model_router as model_router_module
from app.bootstrap.runtime import build_runtime
from app.bootstrap.skills import bootstrap_builtin_skills
from app.bootstrap.catalog import bootstrap_demo_catalog
from app.models.app_blueprint import AppBlueprint
from app.models.practice_review import PracticeReviewRequest
from app.models.skill_blueprint import SkillBlueprint
from app.models.skill_suggestion import SkillSuggestionRequest
from app.models.app_refinement import SuggestedSkillRefinementRequest, SuggestedSkillRefinementClosureRequest
from app.models.patch_proposal import SelfRefinementRequest
from app.models.proposal_review import ProposalReviewRequest
from app.models.priority_analysis import PriorityAnalysisRequest
from app.models.refinement_loop import RefinementLoopRequest
from app.api.operator_filters import build_refinement_filter, build_workflow_observability_filter
from app.models.policy_authority import AuthorityPolicyRecord
from app.models.skill_diagnostics import SkillDiagnostic, SkillDiagnosticError, SkillRetryAdviceRequest
from app.services.priority_analysis import PriorityAnalysisError
from app.services.skill_factory import SkillFactoryError
from app.services.skill_control import SkillControlError
from app.services.skill_runtime import SkillRuntimeError
from app.services.app_registry import AppRegistryError
from app.services.app_installer import AppInstallerError
from app.services.lifecycle import LifecycleError
from app.services.runtime_host import RuntimeHostError
from app.services.workflow_executor import WorkflowExecutorError
from app.services.skill_retry_advisor import SkillRetryAdvisorService
from app.services.core_skill_toolchain import (
    CoreAcceptanceReportSkill,
    CoreArchiveSummarySkill,
    CoreCostAnalyzerSkill,
    CoreReplaySelectorSkill,
)


def create_isolated_test_client(tmp_path: Path) -> TestClient:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        """
models:
  cheap:
    provider: openai_compatible
    base_url: https://example.com/v1
    model: cheap-model
    api_key_env: OPENAI_API_KEY
routing:
  callers:
    default:
      default_model: cheap
model:
  provider: openai_compatible
  base_url: https://example.com/v1
  model: cheap-model
  api_key_env: OPENAI_API_KEY
""".strip()
        + "\n",
        encoding="utf-8",
    )
    os.environ.setdefault("AGENTSYSTEM_CONFIG_DIR", str(config_dir))
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    model_router_module.DEFAULT_CONFIG_PATH = config_dir / "config.yaml"

    app = FastAPI(title="AgentSystem App OS", version="0.1.0-test")
    services = build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )

    bootstrap_builtin_skills(services["skill_runtime"], services)
    bootstrap_demo_catalog(services["app_registry"], services["app_catalog"])
    retry_advisor = SkillRetryAdvisorService()
    core_replay_selector = CoreReplaySelectorSkill(services["telemetry_service"])
    core_cost_analyzer = CoreCostAnalyzerSkill(services["telemetry_service"])
    core_acceptance_report = CoreAcceptanceReportSkill(services["evaluation_summary_service"])
    core_archive_summary = CoreArchiveSummarySkill()
    services["core_replay_selector"] = core_replay_selector
    services["core_cost_analyzer"] = core_cost_analyzer
    services["core_acceptance_report"] = core_acceptance_report
    services["core_archive_summary"] = core_archive_summary
    app.state.services = services

    def _register(method: str, path: str):
        def decorator(func):
            getattr(app, method)(path)(func)
            return func
        return decorator


    @_register("get", "/health")
    def health() -> dict:
        return {"status": "ok"}

    @_register("get", "/version")
    def version() -> dict:
        return {"version": "0.1.0"}

    @_register("get", "/skills")
    def list_skills() -> list[dict]:
        return [item.model_dump(mode="json") for item in services["skill_control"].list_skills()]

    @_register("get", "/skills/{skill_id}")
    def get_skill(skill_id: str) -> dict:
        try:
            return services["skill_control"].get_skill(skill_id).model_dump(mode="json")
        except SkillControlError as error:
            raise map_domain_error(error) from error

    @_register("post", "/skills/{skill_id}/replace")
    def replace_skill(skill_id: str, payload: dict) -> dict:
        try:
            return services["skill_control"].replace_skill(
                skill_id=skill_id,
                version=payload["version"],
                content=payload["content"],
                note=payload.get("note", ""),
            ).model_dump(mode="json")
        except SkillControlError as error:
            raise map_domain_error(error) from error

    @_register("get", "/skills/{skill_id}/versions")
    def list_skill_versions(skill_id: str) -> list[dict]:
        try:
            entry = services["skill_control"].get_skill(skill_id)
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

    @_register("get", "/skills/{skill_id}/compare")
    def compare_skill_versions(skill_id: str, from_version: str, to_version: str) -> dict:
        try:
            entry = services["skill_control"].get_skill(skill_id)
            if entry.origin != "generated":
                raise SkillFactoryError(f"Only generated skills support compare: {skill_id}")
            return services["skill_factory"].compare_generated_skill_versions(skill_id, from_version, to_version).model_dump(mode="json")
        except (SkillControlError, SkillFactoryError, ValueError) as error:
            raise map_domain_error(error) from error

    @_register("post", "/skills/{skill_id}/revisions/{version}/activate")
    def activate_generated_skill_revision(skill_id: str, version: str, payload: dict | None = None) -> dict:
        try:
            reviewer = (payload or {}).get("reviewer", "")
            return services["skill_factory"].activate_generated_skill_revision(skill_id, version, reviewer=reviewer)
        except (SkillControlError, SkillFactoryError, ValueError) as error:
            raise map_domain_error(error) from error

    @_register("post", "/skills/{skill_id}/revise")
    def revise_generated_skill(skill_id: str, payload: dict) -> dict:
        from app.models.skill_creation import GeneratedSkillRevisionRequest
        try:
            return services["skill_factory"].revise_generated_skill(skill_id, GeneratedSkillRevisionRequest(**payload)).model_dump(mode="json")
        except (SkillDiagnosticError, SkillControlError, SkillRuntimeError, SkillFactoryError, ValueError) as error:
            raise map_domain_error(error) from error

    @_register("post", "/skills/{skill_id}/rollback")
    def rollback_skill(skill_id: str, payload: dict) -> dict:
        try:
            entry = services["skill_control"].get_skill(skill_id)
            if entry.origin == "generated":
                return services["skill_factory"].rollback_generated_skill(
                    skill_id,
                    payload["target_version"],
                    reviewer=payload.get("reviewer", ""),
                    rollback_reason=payload.get("rollback_reason", ""),
                )
            return services["skill_control"].rollback_skill(skill_id, payload["target_version"]).model_dump(mode="json")
        except (SkillControlError, SkillFactoryError, ValueError) as error:
            raise map_domain_error(error) from error

    @_register("get", "/catalog/apps")
    def list_catalog_apps() -> list[dict]:
        return [item.model_dump(mode="json") for item in services["app_catalog"].list_apps()]

    @_register("post", "/requirements/clarify")
    def clarify_requirement(payload: dict) -> dict:
        return services["requirement_clarifier"].clarify(payload["text"]).model_dump(mode="json")

    @_register("post", "/requirements/readiness")
    def requirement_readiness(payload: dict) -> dict:
        text = payload.get("text", "")
        result = services["requirement_clarifier"].readiness(text)
        services["log_evidence"].ingest_clarify_unresolved(
            request_text=text,
            requirement_type=result["requirement_type"],
            readiness=result["readiness"],
            missing_fields=result["missing_fields"],
        )
        return result

    @_register("post", "/requirements/blueprint-draft")
    def requirement_blueprint_draft(payload: dict) -> dict:
        text = payload.get("text", "")
        spec = services["requirement_clarifier"].clarify(text)
        try:
            return services["requirement_blueprint_builder"].build_blueprint_draft(spec).model_dump(mode="json")
        except ValueError as error:
            raise map_domain_error(error) from error

    @_register("post", "/blueprints/validate")
    def validate_blueprint(payload: dict) -> dict:
        from app.models.app_blueprint import AppBlueprint
        return services["blueprint_validation"].validate(AppBlueprint(**payload))

    @_register("get", "/evidence/signals")
    def get_evidence_signals(limit: int | None = None) -> dict:
        return services["log_evidence"].list_signals(limit=limit).model_dump(mode="json")

    @_register("get", "/evidence/promoted")
    def get_promoted_evidence(limit: int | None = None) -> dict:
        return services["log_evidence"].list_promoted_evidence(limit=limit).model_dump(mode="json")

    @_register("get", "/evidence/index")
    def get_evidence_index(limit: int | None = None) -> dict:
        return services["log_evidence"].list_index_entries(limit=limit).model_dump(mode="json")

    @_register("get", "/evidence/stats")
    def get_evidence_stats() -> dict:
        return services["log_evidence"].get_stats_summary()

    @_register("post", "/interaction/command")
    def handle_interaction_command(payload: dict) -> dict:
        from app.models.interaction import UserCommand
        return services["interaction_gateway"].handle_command(UserCommand(**payload)).model_dump(mode="json")

    @_register("get", "/runtime/persistence")
    def get_runtime_persistence_snapshot() -> dict:
        runtime_store = services["runtime_store"]
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

    @_register("post", "/apps/{app_instance_id}/workflows/execute")
    def execute_workflow(app_instance_id: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        return services["workflow_executor"].execute_workflow(
            app_instance_id=app_instance_id,
            workflow_id=payload.get("workflow_id"),
            trigger=payload.get("trigger", "manual"),
            inputs=payload.get("inputs", {}),
        ).model_dump(mode="json")

    @_register("post", "/apps/{app_instance_id}/workflows/resume-last-interrupted")
    def resume_last_interrupted(app_instance_id: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        return services["workflow_executor"].resume_last_interrupted(
            app_instance_id,
            resume_inputs=payload.get("resume_inputs", {}),
        ).model_dump(mode="json")

    @_register("post", "/apps/{app_instance_id}/workflows/retry-last-failure")
    def retry_last_failure(app_instance_id: str) -> dict:
        return services["workflow_executor"].retry_last_failure(app_instance_id).model_dump(mode="json")

    @_register("get", "/workflows/history")
    def list_workflow_history(app_instance_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["workflow_executor"].list_history(app_instance_id)]

    @_register("get", "/workflows/failures")
    def list_workflow_failures(
        app_instance_id: str | None = None,
        workflow_id: str | None = None,
        failed_step_id: str | None = None,
    ) -> list[dict]:
        failures = services["workflow_executor"].list_recent_failures(app_instance_id)
        if workflow_id is not None:
            failures = [item for item in failures if item.workflow_id == workflow_id]
        if failed_step_id is not None:
            failures = [item for item in failures if failed_step_id in item.failed_step_ids]
        return [item.model_dump(mode="json") for item in failures]

    @_register("get", "/workflows/latest")
    def get_latest_workflow_execution(app_instance_id: str | None = None) -> dict:
        history = services["workflow_executor"].list_history(app_instance_id)
        if not history:
            return {"execution": None}
        latest = max(history, key=lambda item: item.completed_at)
        return {"execution": latest.model_dump(mode="json")}

    @_register("get", "/workflows/diagnostics")
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
        return services["workflow_observability"].get_diagnostics_summary(
            app_instance_id=filters.app_instance_id,
            workflow_id=filters.workflow_id,
            failed_step_id=filters.failed_step_id,
        ).model_dump(mode="json")

    @_register("get", "/workflows/latest-recovery")
    def get_latest_workflow_recovery(app_instance_id: str, workflow_id: str | None = None) -> dict:
        recovery = services["workflow_observability"].get_latest_recovery_summary(app_instance_id, workflow_id=workflow_id)
        return {"recovery": None if recovery is None else recovery.model_dump(mode="json")}

    @_register("get", "/workflows/overview")
    def get_workflow_overview(app_instance_id: str, workflow_id: str | None = None, failed_step_id: str | None = None) -> dict:
        filters = build_workflow_observability_filter(
            app_instance_id=app_instance_id,
            workflow_id=workflow_id,
            failed_step_id=failed_step_id,
        )
        return services["workflow_observability"].get_overview(
            app_instance_id=filters.app_instance_id,
            workflow_id=filters.workflow_id,
            failed_step_id=filters.failed_step_id,
        ).model_dump(mode="json")

    @_register("get", "/workflows/observability-history")
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
        return services["workflow_observability"].list_observability_history(
            app_instance_id=filters.app_instance_id,
            workflow_id=filters.workflow_id,
            failed_step_id=filters.failed_step_id,
            limit=filters.limit,
            unresolved_only=filters.unresolved_only,
            since=filters.since,
            cursor=filters.cursor,
        ).model_dump(mode="json")

    @_register("get", "/workflows/timeline")
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
        return services["workflow_observability"].list_timeline_events(
            app_instance_id=filters.app_instance_id,
            workflow_id=filters.workflow_id,
            failed_step_id=filters.failed_step_id,
            limit=filters.limit,
            unresolved_only=filters.unresolved_only,
            since=filters.since,
            cursor=filters.cursor,
        ).model_dump(mode="json")

    @_register("get", "/workflows/stats")
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
        return services["workflow_observability"].get_stats_summary(
            app_instance_id=filters.app_instance_id,
            workflow_id=filters.workflow_id,
            failed_step_id=filters.failed_step_id,
            since=filters.since,
        ).model_dump(mode="json")

    @_register("get", "/workflows/dashboard")
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
        return services["workflow_observability"].get_dashboard_summary(
            app_instance_id=filters.app_instance_id,
            workflow_id=filters.workflow_id,
            failed_step_id=filters.failed_step_id,
            since=filters.since,
            timeline_limit=timeline_limit,
        ).model_dump(mode="json")

    @_register("get", "/data/namespaces/{namespace_id}/records")
    def list_records(namespace_id: str) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["app_data_store"].list_records(namespace_id)]

    @_register("post", "/workflow-subscriptions")
    def create_workflow_subscription(payload: dict) -> dict:
        from app.models.workflow_subscription import WorkflowEventSubscription
        return services["workflow_subscription"].subscribe(WorkflowEventSubscription(**payload)).model_dump(mode="json")

    @_register("get", "/data/namespaces")
    def list_namespaces(app_instance_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["app_data_store"].list_namespaces(app_instance_id)]

    @_register("post", "/data/namespaces/{namespace_id}/records")
    def put_record(namespace_id: str, payload: dict) -> dict:
        return services["app_data_store"].put_record(
            namespace_id=namespace_id,
            key=payload["key"],
            value=payload["value"],
            tags=payload.get("tags", []),
        ).model_dump(mode="json")

    @_register("get", "/events")
    def list_events(event_name: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["event_bus"].list_events(event_name)]

    @_register("get", "/skill-runtime/failures")
    def list_skill_runtime_failures() -> list[dict]:
        return [item.model_dump(mode="json") for item in services["skill_runtime"].list_failures()]

    @_register("get", "/telemetry/interactions/{interaction_id}")
    def get_telemetry_interaction(interaction_id: str) -> dict:
        item = services["telemetry_service"].get_interaction(interaction_id)
        if item is None:
            raise HTTPException(status_code=404, detail="telemetry interaction not found")
        return item.model_dump(mode="json")

    @_register("get", "/telemetry/feedback")
    def list_telemetry_feedback(scope_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["telemetry_service"].list_feedback(scope_id=scope_id)]

    @_register("get", "/telemetry/version-bindings/{interaction_id}")
    def get_version_binding(interaction_id: str) -> dict:
        item = services["telemetry_service"].get_version_binding(interaction_id)
        if item is None:
            raise HTTPException(status_code=404, detail="version binding not found")
        return item.model_dump(mode="json")

    @_register("get", "/evaluation/candidates/{candidate_id}")
    def get_candidate_evaluation(candidate_id: str) -> dict:
        item = services["evaluation_summary_service"].get(candidate_id)
        if item is None:
            raise HTTPException(status_code=404, detail="candidate evaluation not found")
        return item.model_dump(mode="json")

    @_register("get", "/core-skills/replay/failed-interactions")
    def list_failed_replay_candidates() -> dict:
        return {"interaction_ids": services["core_replay_selector"].select_failed_interactions()}

    @_register("get", "/core-skills/cost/{app_id}")
    def summarize_app_cost(app_id: str) -> dict:
        return services["core_cost_analyzer"].summarize_app_cost(app_id)

    @_register("get", "/core-skills/acceptance/{candidate_id}")
    def get_acceptance_report(candidate_id: str) -> dict:
        return services["core_acceptance_report"].build_report(candidate_id)

    @_register("get", "/core-skills/archive/{candidate_id}")
    def get_archive_summary(candidate_id: str) -> dict:
        item = services["evaluation_summary_service"].get(candidate_id)
        if item is None:
            raise HTTPException(status_code=404, detail="candidate evaluation not found")
        return services["core_archive_summary"].summarize_evaluation(item)

    @_register("get", "/events/subscriptions")
    def list_event_subscriptions(event_name: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["scheduler"].list_subscriptions(event_name)]

    @_register("post", "/events/subscriptions")
    def create_event_subscription(payload: dict) -> dict:
        from app.models.event_bus import EventSubscription
        return services["event_bus"].subscribe(EventSubscription(**payload)).model_dump(mode="json")

    @_register("post", "/events/publish")
    def publish_event(payload: dict) -> dict:
        result = services["event_bus"].publish(
            payload["event_name"],
            source=payload.get("source", "system"),
            app_instance_id=payload.get("app_instance_id"),
            payload=payload.get("payload", {}),
        )
        workflow_runs = services["workflow_subscription"].trigger(
            event_name=payload["event_name"],
            payload=payload.get("payload", {}),
        )
        response = result.model_dump(mode="json")
        response["workflow_runs"] = [item.model_dump(mode="json") for item in workflow_runs]
        return response

    @_register("post", "/practice/review")
    def practice_review(payload: dict) -> dict:
        from app.models.practice_review import PracticeReviewRequest
        return services["practice_review"].review(PracticeReviewRequest(**payload)).model_dump(mode="json")

    @_register("post", "/skills/suggest-from-experience")
    def suggest_from_experience(payload: dict) -> dict:
        from app.models.skill_suggestion import SkillSuggestionRequest
        return services["skill_suggestion"].suggest(SkillSuggestionRequest(**payload)).model_dump(mode="json")

    @_register("post", "/apps/refine-from-suggested-skills")
    def refine_from_suggested_skills(payload: dict) -> dict:
        from app.models.app_refinement import SuggestedSkillRefinementRequest
        return services["app_refinement"].build_app_from_suggested_skills(
            SuggestedSkillRefinementRequest(**payload)
        ).model_dump(mode="json")

    @_register("post", "/apps/refine-from-suggested-skills/closure")
    def refine_from_suggested_skills_closure(payload: dict) -> dict:
        from app.models.app_refinement import SuggestedSkillRefinementClosureRequest
        return services["app_refinement_orchestrator"].refine_closure(
            SuggestedSkillRefinementClosureRequest(**payload)
        ).model_dump(mode="json")

    @_register("get", "/registry/apps")
    def list_registry_apps() -> list[dict]:
        return [item.model_dump(mode="json") for item in services["app_registry"].list_entries()]

    @_register("get", "/registry/apps/{blueprint_id}/summary")
    def get_app_control_plane_summary(blueprint_id: str) -> dict:
        return services["app_registry"].get_control_plane_summary(blueprint_id).model_dump(mode="json")

    @_register("get", "/registry/apps/overview")
    def get_app_registry_overview(
        app_shape: str | None = None,
        has_draft: bool | None = None,
        rollback_available: bool | None = None,
        limit: int | None = None,
    ) -> dict:
        return services["app_registry"].get_registry_overview(
            app_shape=app_shape,
            has_draft=has_draft,
            rollback_available=rollback_available,
            limit=limit,
        ).model_dump(mode="json")

    @_register("get", "/registry/apps/attention")
    def get_app_registry_attention(limit: int | None = None) -> dict:
        return services["app_registry"].get_attention_summary(limit=limit).model_dump(mode="json")

    @_register("post", "/registry/apps/{blueprint_id}/attention-actions")
    def record_app_attention_action(blueprint_id: str, payload: dict[str, str]) -> dict:
        return services["app_registry"].record_operator_action(
            blueprint_id=blueprint_id,
            attention_reason=payload["attention_reason"],
            action=payload["action"],
            reviewer=payload.get("reviewer", ""),
            note=payload.get("note", ""),
        ).model_dump(mode="json")

    @_register("post", "/registry/apps/{blueprint_id}/releases")
    def add_app_release(blueprint_id: str, payload: dict) -> dict:
        return services["app_registry"].add_release(
            blueprint_id,
            version=payload["version"],
            note=payload.get("note", ""),
            reviewer=payload.get("reviewer", ""),
            activate_immediately=payload.get("activate_immediately", False),
        ).model_dump(mode="json")

    @_register("post", "/registry/apps/{blueprint_id}/releases/{version}/activate")
    def activate_app_release(blueprint_id: str, version: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        services["policy_authority"].enforce(
            scope="app_activate",
            reviewer=payload.get("reviewer", ""),
            reason=payload.get("reason", ""),
            automatic=False,
        )
        return services["app_registry"].activate_release(
            blueprint_id,
            version,
            reviewer=payload.get("reviewer", ""),
        ).model_dump(mode="json")

    @_register("post", "/registry/apps/{blueprint_id}/rollback")
    def rollback_app_release(blueprint_id: str, payload: dict) -> dict:
        services["policy_authority"].enforce(
            scope="app_rollback",
            reviewer=payload.get("reviewer", ""),
            reason=payload.get("rollback_reason", ""),
            automatic=False,
        )
        return services["app_registry"].rollback_release(
            blueprint_id,
            payload["target_version"],
            reviewer=payload.get("reviewer", ""),
            rollback_reason=payload.get("rollback_reason", ""),
        ).model_dump(mode="json")

    @_register("post", "/registry/apps/{blueprint_id}/install")
    def install_app(blueprint_id: str, payload: dict) -> dict:
        return services["app_installer"].install_app(blueprint_id, user_id=payload["user_id"]).model_dump(mode="json")

    @_register("get", "/apps")
    def list_apps() -> list[dict]:
        return [item.model_dump(mode="json") for item in services["lifecycle"].list_instances()]

    @_register("post", "/apps")
    def create_app_instance(payload: dict) -> dict:
        from app.models.app_instance import AppInstance
        instance = AppInstance(**payload)
        services["runtime_host"].register_instance(instance)
        return instance.model_dump(mode="json")

    @_register("get", "/apps/{app_instance_id}")
    def get_app_instance(app_instance_id: str) -> dict:
        try:
            return services["lifecycle"].get_instance(app_instance_id).model_dump(mode="json")
        except Exception as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @_register("get", "/apps/{app_instance_id}/events")
    def list_app_events(app_instance_id: str) -> list[dict]:
        try:
            return [item.model_dump(mode="json") for item in services["lifecycle"].list_events(app_instance_id)]
        except Exception as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @_register("post", "/apps/{app_instance_id}/actions/{action}")
    def apply_app_action(app_instance_id: str, action: str, payload: dict | None = None) -> dict:
        reason = (payload or {}).get("reason", "")
        try:
            if action == "validate":
                return services["lifecycle"].transition(app_instance_id, "validate", reason=reason).model_dump(mode="json")
            if action == "compile":
                return services["lifecycle"].transition(app_instance_id, "compile", reason=reason).model_dump(mode="json")
            if action == "install":
                return services["lifecycle"].transition(app_instance_id, "install", reason=reason).model_dump(mode="json")
            if action == "upgrade":
                return services["lifecycle"].transition(app_instance_id, "upgrade", reason=reason).model_dump(mode="json")
            if action == "archive":
                return services["lifecycle"].transition(app_instance_id, "archive", reason=reason).model_dump(mode="json")
            if action == "start":
                return services["runtime_host"].start(app_instance_id, reason=reason).model_dump(mode="json")
            if action == "pause":
                return services["runtime_host"].pause(app_instance_id, reason=reason).model_dump(mode="json")
            if action == "resume":
                return services["runtime_host"].resume(app_instance_id, reason=reason).model_dump(mode="json")
            if action == "stop":
                return services["runtime_host"].stop(app_instance_id, reason=reason).model_dump(mode="json")
            if action == "fail":
                return services["runtime_host"].mark_failed(app_instance_id, reason=reason).model_dump(mode="json")
            raise HTTPException(status_code=400, detail=f"Unsupported app action: {action}")
        except HTTPException:
            raise
        except Exception as error:
            message = str(error)
            status = 404 if "not found" in message.lower() else 400
            raise HTTPException(status_code=status, detail=message) from error

    @_register("post", "/apps/{app_instance_id}/tasks")
    def enqueue_runtime_task(app_instance_id: str, payload: dict[str, str]) -> dict:
        try:
            tasks = services["runtime_host"].enqueue_task(app_instance_id, payload["task_name"])
            return {"app_instance_id": app_instance_id, "pending_tasks": tasks}
        except Exception as error:
            message = str(error)
            status = 404 if "not found" in message.lower() else 400
            raise HTTPException(status_code=status, detail=message) from error

    @_register("post", "/apps/{app_instance_id}/healthcheck")
    def healthcheck_app(app_instance_id: str, payload: dict[str, bool] | None = None) -> dict:
        healthy = True if payload is None else payload.get("healthy", True)
        try:
            return services["runtime_host"].healthcheck(app_instance_id, healthy=healthy).model_dump(mode="json")
        except Exception as error:
            message = str(error)
            status = 404 if "not found" in message.lower() else 400
            raise HTTPException(status_code=status, detail=message) from error

    @_register("get", "/apps/{app_instance_id}/runtime")
    def get_runtime_overview(app_instance_id: str) -> dict:
        try:
            return services["runtime_host"].get_overview(app_instance_id).model_dump(mode="json")
        except Exception as error:
            message = str(error)
            status = 404 if "not found" in message.lower() else 400
            raise HTTPException(status_code=status, detail=message) from error

    @_register("get", "/app-contexts")
    def list_app_contexts() -> list[dict]:
        return [item.model_dump(mode="json") for item in services["app_context_store"].list_contexts()]

    @_register("get", "/app-contexts/{app_instance_id}")
    def get_app_context(app_instance_id: str, include_runtime: bool = False) -> dict:
        if include_runtime:
            view = services["app_context_store"].get_runtime_view(app_instance_id)
            return {
                "context": view["context"].model_dump(mode="json"),
                "runtime": None if view["runtime"] is None else view["runtime"].model_dump(mode="json"),
            }
        return services["app_context_store"].get_context(app_instance_id).model_dump(mode="json")

    @_register("post", "/app-contexts/{app_instance_id}")
    def update_app_context(app_instance_id: str, payload: dict) -> dict:
        return services["app_context_store"].update_context(
            app_instance_id=app_instance_id,
            current_goal=payload.get("current_goal"),
            current_stage=payload.get("current_stage"),
        ).model_dump(mode="json")

    @_register("post", "/app-contexts/{app_instance_id}/entries")
    def append_context_entry(app_instance_id: str, payload: dict) -> dict:
        return services["app_context_store"].append_entry(
            app_instance_id=app_instance_id,
            section=payload["section"],
            key=payload["key"],
            value=payload.get("value"),
            tags=payload.get("tags", []),
        ).model_dump(mode="json")

    @_register("post", "/app-contexts/{app_instance_id}/compact")
    def compact_app_context(app_instance_id: str) -> dict:
        return services["context_compaction"].compact(app_instance_id).model_dump(mode="json")

    @_register("get", "/app-contexts/{app_instance_id}/working-set")
    def get_app_working_set(app_instance_id: str) -> dict:
        return services["context_compaction"].build_working_set(app_instance_id).model_dump(mode="json")

    @_register("get", "/app-contexts/{app_instance_id}/layers")
    def get_app_context_layers(app_instance_id: str) -> dict:
        return services["context_compaction"].list_layers(app_instance_id)

    @_register("post", "/app-contexts/{app_instance_id}/policy")
    def set_app_context_policy(app_instance_id: str, payload: dict) -> dict:
        from app.models.context_policy import ContextCompactionPolicy
        return services["context_compaction"].set_policy(
            ContextCompactionPolicy(
                app_instance_id=app_instance_id,
                max_context_entries=payload.get("max_context_entries", 20),
                compact_on_workflow_complete=payload.get("compact_on_workflow_complete", True),
                compact_on_workflow_failure=payload.get("compact_on_workflow_failure", True),
                compact_on_stage_change=payload.get("compact_on_stage_change", False),
            )
        ).model_dump(mode="json")

    @_register("post", "/self-refinement/propose")
    def self_refinement_propose(payload: dict) -> dict:
        from app.models.patch_proposal import SelfRefinementRequest
        result = services["self_refinement"].propose(SelfRefinementRequest(**payload))
        services["proposal_review"].register_proposals(result)
        return result.model_dump(mode="json")

    @_register("post", "/self-refinement/analyze-priority")
    def analyze_priority(payload: dict) -> dict:
        from app.models.priority_analysis import PriorityAnalysisRequest
        return services["priority_analysis"].analyze(PriorityAnalysisRequest(**payload)).model_dump(mode="json")

    @_register("get", "/self-refinement/proposals")
    def list_proposals(app_instance_id: str) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["proposal_review"].list_proposals(app_instance_id)]

    @_register("post", "/self-refinement/review")
    def review_proposal(payload: dict) -> dict:
        return services["proposal_review"].review(ProposalReviewRequest(**payload)).model_dump(mode="json")

    @_register("post", "/registry/apps")
    def register_blueprint(payload: dict) -> dict:
        return services["app_registry"].register_blueprint(AppBlueprint(**payload)).model_dump(mode="json")

    @_register("get", "/self-refinement/hypotheses")
    def list_hypotheses(app_instance_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["refinement_memory"].list_hypotheses(app_instance_id)]

    @_register("get", "/self-refinement/experiments")
    def list_experiments(hypothesis_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["refinement_memory"].list_experiments(hypothesis_id)]

    @_register("get", "/self-refinement/verifications")
    def list_verifications(hypothesis_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["refinement_memory"].list_verifications(hypothesis_id)]

    @_register("get", "/self-refinement/decisions")
    def list_decisions(hypothesis_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["refinement_memory"].list_decisions(hypothesis_id)]

    @_register("get", "/self-refinement/rollout-queue")
    def list_rollout_queue(app_instance_id: str | None = None, hypothesis_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["refinement_memory"].list_queue(app_instance_id, hypothesis_id)]

    @_register("get", "/self-refinement/overview")
    def get_overview(app_instance_id: str) -> dict:
        return services["refinement_memory"].build_overview(app_instance_id).model_dump(mode="json")

    @_register("get", "/self-refinement/rollout-queue-page")
    def get_rollout_queue_page(
        app_instance_id: str | None = None,
        hypothesis_id: str | None = None,
        proposal_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> dict:
        return services["refinement_memory"].list_queue_page(
            build_refinement_filter(
                app_instance_id=app_instance_id,
                hypothesis_id=hypothesis_id,
                proposal_id=proposal_id,
                status=status,
                limit=limit,
            )
        ).model_dump(mode="json")

    @_register("get", "/self-refinement/failed-hypotheses-page")
    def get_failed_hypotheses_page(
        app_instance_id: str | None = None,
        hypothesis_id: str | None = None,
        proposal_id: str | None = None,
        limit: int | None = None,
    ) -> dict:
        return services["refinement_memory"].list_failed_hypothesis_page(
            build_refinement_filter(
                app_instance_id=app_instance_id,
                hypothesis_id=hypothesis_id,
                proposal_id=proposal_id,
                limit=limit,
            )
        ).model_dump(mode="json")

    @_register("get", "/self-refinement/stats")
    def get_stats(
        app_instance_id: str | None = None,
        hypothesis_id: str | None = None,
        proposal_id: str | None = None,
        verification_outcome: str | None = None,
    ) -> dict:
        return services["refinement_memory"].get_stats_summary(
            build_refinement_filter(
                app_instance_id=app_instance_id,
                hypothesis_id=hypothesis_id,
                proposal_id=proposal_id,
                verification_outcome=verification_outcome,
            )
        ).model_dump(mode="json")

    @_register("get", "/self-refinement/governance-dashboard")
    def get_governance_dashboard(
        app_instance_id: str | None = None,
        hypothesis_id: str | None = None,
        proposal_id: str | None = None,
        status: str | None = None,
        verification_outcome: str | None = None,
        recent_limit: int = 5,
    ) -> dict:
        return services["refinement_memory"].get_governance_dashboard(
            build_refinement_filter(
                app_instance_id=app_instance_id,
                hypothesis_id=hypothesis_id,
                proposal_id=proposal_id,
                status=status,
                verification_outcome=verification_outcome,
            ),
            recent_limit=recent_limit,
        ).model_dump(mode="json")

    @_register("get", "/self-refinement/operator-summary")
    def get_operator_summary(app_instance_id: str, recent_limit: int = 5) -> dict:
        try:
            priority = services["priority_analysis"].analyze(PriorityAnalysisRequest(app_instance_id=app_instance_id))
        except PriorityAnalysisError:
            priority = None
        return services["refinement_memory"].build_operator_summary(
            app_instance_id=app_instance_id,
            proposals=services["proposal_review"].list_proposals(app_instance_id),
            reviews=services["proposal_review"].list_reviews(),
            priority=priority,
            recent_limit=recent_limit,
        ).model_dump(mode="json")

    @_register("get", "/self-refinement/dashboard")
    def get_refinement_dashboard(app_instance_id: str, limit: int = 5) -> dict:
        return services["refinement_memory"].build_dashboard(app_instance_id, limit=limit).model_dump(mode="json")

    @_register("get", "/self-refinement/failed-hypotheses")
    def list_failed_hypotheses(app_instance_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["refinement_memory"].list_failed_hypotheses(app_instance_id=app_instance_id)]

    @_register("post", "/self-refinement/loop")
    def run_refinement_loop(payload: dict) -> dict:
        return services["refinement_loop"].run(RefinementLoopRequest(**payload)).model_dump(mode="json")


    @_register("post", "/skills/create")
    def create_skill(payload: dict) -> dict:
        from app.models.skill_creation import SkillCreationRequest
        try:
            return services["skill_factory"].create_skill(SkillCreationRequest(**payload)).model_dump(mode="json")
        except (SkillDiagnosticError, SkillControlError, SkillRuntimeError, ValueError) as error:
            raise map_domain_error(error) from error

    @_register("post", "/skills/diagnose-retry")
    def diagnose_retry(payload: dict) -> dict:
        return retry_advisor.build_retry_advice(SkillRetryAdviceRequest(**payload).diagnostic).model_dump(mode="json")

    @_register("get", "/skill-risk/events")
    def list_skill_risk_events(skill_id: str | None = None) -> list[dict]:
        return [item.model_dump(mode="json") for item in services["skill_risk_policy"].list_events(skill_id=skill_id)]

    @_register("get", "/skill-risk/decisions")
    def list_skill_risk_decisions() -> list[dict]:
        return [item.model_dump(mode="json") for item in services["skill_risk_policy"].list_decisions()]

    @_register("get", "/skill-risk/stats")
    def get_skill_risk_stats() -> dict:
        return services["skill_risk_policy"].get_stats_summary().model_dump(mode="json")

    @_register("get", "/skill-risk/dashboard")
    def get_skill_risk_dashboard(recent_limit: int = 5) -> dict:
        return services["skill_risk_policy"].get_dashboard(recent_limit=recent_limit).model_dump(mode="json")

    @_register("post", "/skill-risk/{skill_id}/approve")
    def approve_skill_risk_override(skill_id: str, reviewer: str, reason: str = "", scope: str = "generated_app_assembly") -> dict:
        return services["skill_risk_policy"].approve_override(
            skill_id=skill_id,
            reviewer=reviewer,
            reason=reason,
            scope=scope,
        ).model_dump(mode="json")

    @_register("post", "/skill-risk/{skill_id}/revoke")
    def revoke_skill_risk_override(skill_id: str, reviewer: str, reason: str = "", scope: str = "generated_app_assembly") -> dict:
        return services["skill_risk_policy"].revoke_override(skill_id=skill_id, reviewer=reviewer, reason=reason).model_dump(mode="json")

    @_register("post", "/apps/from-skills")
    def create_app_from_skills(payload: dict) -> dict:
        from app.models.skill_creation import AppFromSkillsRequest
        try:
            blueprint, result = services["skill_factory"].build_blueprint_from_skills(AppFromSkillsRequest(**payload))
            services["app_registry"].register_blueprint(blueprint)
            return {
                "blueprint": blueprint.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
            }
        except (SkillDiagnosticError, AppRegistryError, SkillFactoryError, ValueError) as error:
            raise map_domain_error(error) from error

    @_register("post", "/apps/from-skills/install-run")
    def create_install_and_run_app_from_skills(payload: dict) -> dict:
        from app.models.skill_creation import AppFromSkillsInstallRunRequest
        request = AppFromSkillsInstallRunRequest(**payload)
        try:
            blueprint, result = services["skill_factory"].build_blueprint_from_skills(request)
            services["app_registry"].register_blueprint(blueprint)
            install = services["app_installer"].install_app(blueprint_id=blueprint.id, user_id=request.user_id)
            execution = services["workflow_executor"].execute_workflow(
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

    @_register("get", "/skill-runtime/executions")
    def list_skill_runtime_executions() -> list[dict]:
        return [item.model_dump(mode="json") for item in services["skill_runtime"].list_executions()]

    @_register("post", "/skill-blueprints")
    def create_skill_blueprint(payload: dict) -> dict:
        return services["experience_store"].add_skill_blueprint(SkillBlueprint(**payload)).model_dump(mode="json")

    @_register("post", "/skill-blueprints/{skill_id}/materialize")
    def materialize_skill_blueprint(skill_id: str, payload: dict) -> dict:
        from app.models.skill_creation import BlueprintMaterializationRequest
        request = BlueprintMaterializationRequest(**payload)
        try:
            blueprint = services["experience_store"].get_skill_blueprint(skill_id)
            safety_profile = blueprint.safety_profile or {}
            requested_adapter_kind = request.adapter_kind
            effective_adapter_kind, governance_adjusted, governance_reason = services["skill_factory"].choose_adapter_kind_for_blueprint(
                blueprint,
                requested_adapter_kind,
            )
            if (
                effective_adapter_kind == "script"
                and request.command
                and request.command[0] in {"bash", "sh"}
                and safety_profile.get("allow_shell") is False
            ):
                active_override = services["skill_risk_policy"].get_active_override(skill_id, scope="blueprint_materialization")
                if active_override is None:
                    raise SkillDiagnosticError(
                        SkillDiagnostic(
                            stage="materialize",
                            kind="policy_blocked",
                            message=f"Skill blueprint '{skill_id}' is gated from shell materialization by safety profile",
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
                    )
            creation_request = services["skill_factory"].build_creation_request_from_blueprint(
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
                active_override = services["skill_risk_policy"].get_active_override(skill_id, scope="blueprint_materialization")
                if active_override is not None:
                    creation_request.manifest_risk.allow_shell = True
                    creation_request.manifest_risk.risk_level = "R2_shell"
                    creation_request.capability_profile.risk_level = "R2_shell"
            creation_result = services["skill_factory"].create_skill(creation_request)
            registered_skill = services["skill_control"].get_skill(creation_result.skill_id)
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
        except (SkillDiagnosticError, SkillControlError, SkillRuntimeError, SkillFactoryError, ValueError) as error:
            raise map_domain_error(error) from error

    @_register("post", "/apps/refine-from-suggested-skills")
    def refine_from_suggested_skills(payload: dict) -> dict:
        return services["app_refinement"].build_app_from_suggested_skills(
            SuggestedSkillRefinementRequest(**payload)
        ).model_dump(mode="json")

    @_register("post", "/apps/refine-from-suggested-skills/closure")
    def refine_from_suggested_skills_closure(payload: dict) -> dict:
        return services["app_refinement_orchestrator"].refine_closure(
            SuggestedSkillRefinementClosureRequest(**payload)
        ).model_dump(mode="json")

    @_register("get", "/policy-authority")
    def get_policy_authority() -> dict:
        return services["policy_authority"].get_summary().model_dump(mode="json")

    @_register("post", "/policy-authority")
    def set_policy_authority(payload: dict) -> dict:
        return services["policy_authority"].set_policy(AuthorityPolicyRecord(**payload)).model_dump(mode="json")

    @_register("get", "/persistence/health")
    def get_persistence_health() -> dict:
        return services["persistence_health"].get_summary().model_dump(mode="json")

    @_register("post", "/schedules")
    def create_schedule(payload: dict) -> dict:
        from app.models.scheduling import ScheduleRecord
        return services["scheduler"].register_schedule(ScheduleRecord(**payload)).model_dump(mode="json")

    @_register("post", "/schedules/trigger/interval")
    def trigger_interval_schedules(payload: dict | None = None) -> list[dict]:
        app_instance_id = None if payload is None else payload.get("app_instance_id")
        return [item.model_dump(mode="json") for item in services["scheduler"].trigger_interval_schedules(app_instance_id)]

    @_register("post", "/supervision/policies")
    def create_supervision_policy(payload: dict) -> dict:
        from app.models.scheduling import SupervisionPolicy
        return services["supervisor"].register_policy(SupervisionPolicy(**payload)).model_dump(mode="json")

    @_register("get", "/supervision/{app_instance_id}")
    def get_supervision_status(app_instance_id: str) -> dict:
        return services["supervisor"].get_status(app_instance_id).model_dump(mode="json")

    @_register("post", "/supervision/{app_instance_id}/observe-failure")
    def observe_failure(app_instance_id: str, payload: dict | None = None) -> dict:
        reason = "" if payload is None else payload.get("reason", "")
        return services["supervisor"].observe_failure(app_instance_id, reason=reason).model_dump(mode="json")

    @_register("post", "/supervision/{app_instance_id}/attempt-restart")
    def attempt_restart(app_instance_id: str) -> dict:
        return services["supervisor"].attempt_restart(app_instance_id).model_dump(mode="json")

    @_register("post", "/supervision/{app_instance_id}/probe-circuit")
    def probe_circuit(app_instance_id: str) -> dict:
        try:
            return services["supervisor"].probe_circuit(app_instance_id).model_dump(mode="json")
        except Exception as error:
            raise map_domain_error(error) from error

    @_register("post", "/supervision/{app_instance_id}/circuit-reset")
    def circuit_reset(app_instance_id: str) -> dict:
        try:
            return services["supervisor"].circuit_reset(app_instance_id).model_dump(mode="json")
        except Exception as error:
            raise map_domain_error(error) from error

    return TestClient(app)
