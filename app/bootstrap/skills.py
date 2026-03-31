from __future__ import annotations

from app.models.app_config import AppConfigRequest
from app.models.context_skill import ContextSkillRequest
from app.models.context_compaction_skill import ContextCompactionSkillRequest
from app.models.evidence_skill import EvidenceSkillRequest
from app.models.requirement_skill import RequirementSkillRequest
from app.models.prompt_selection_skill import PromptSelectionSkillRequest
from app.models.risk_governance_skill import RiskGovernanceSkillRequest
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.system_skill import SystemAuditRequest, SystemStateRequest
from app.models.workflow_insight_skill import WorkflowInsightSkillRequest
from app.services.model_client import OpenAIResponsesClient
from app.services.model_config_loader import ModelConfigLoader
from app.services.skill_runtime import SkillRuntimeService
from app.services.system_skill_registry import register_builtin_handlers, register_builtin_skills


def build_builtin_skill_handlers(services: dict[str, object]) -> dict[str, callable]:
    app_config_service = services["app_config_service"]
    system_state_service = services["system_state_service"]
    system_audit_service = services["system_audit_service"]
    context_skill_service = services["context_skill_service"]
    requirement_clarifier = services["requirement_clarifier"]
    requirement_blueprint_builder = services["requirement_blueprint_builder"]
    log_evidence = services["log_evidence"]
    context_compaction = services["context_compaction"]
    workflow_observability = services["workflow_observability"]
    skill_risk_policy = services["skill_risk_policy"]
    prompt_selection = services["prompt_selection"]
    prompt_invocation = services["prompt_invocation"]

    def demo_echo_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        payload = request.config.get("payload", request.inputs)
        return SkillExecutionResult(
            skill_id=request.skill_id,
            status="completed",
            output={"echo": payload, "inputs": request.inputs, "step_id": request.step_id},
        )

    def system_app_config_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        config_request = AppConfigRequest(**request.inputs)
        result = app_config_service.execute(request.app_instance_id, config_request)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    def system_state_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        state_request = SystemStateRequest(**request.inputs)
        result = system_state_service.execute(request.app_instance_id, state_request)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    def system_audit_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        audit_request = SystemAuditRequest(**request.inputs)
        result = system_audit_service.record(request.app_instance_id, audit_request)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result.model_dump(mode="json"))

    def system_context_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        context_request = ContextSkillRequest(**request.inputs)
        result = context_skill_service.execute(request.app_instance_id, context_request)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=result)

    def model_responses_probe_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        loader = ModelConfigLoader()
        config = loader.load()
        api_key = loader.resolve_api_key(config)
        client = OpenAIResponsesClient(config=config, api_key=api_key)
        result = client.probe(request.inputs["prompt"])
        return SkillExecutionResult(
            skill_id=request.skill_id,
            status="completed",
            output={
                "provider": config.provider,
                "model": config.model,
                "result": result,
            },
        )

    def requirement_capability_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        skill_request = RequirementSkillRequest(**request.inputs)
        if skill_request.operation == "clarify":
            output = requirement_clarifier.clarify(skill_request.text).model_dump(mode="json")
        elif skill_request.operation == "extract":
            output = requirement_clarifier.extract(skill_request.text).model_dump(mode="json")
        elif skill_request.operation == "readiness":
            output = requirement_clarifier.readiness(skill_request.text)
            if skill_request.include_evidence_ingest:
                log_evidence.ingest_clarify_unresolved(
                    request_text=skill_request.text,
                    requirement_type=output["requirement_type"],
                    readiness=output["readiness"],
                    missing_fields=output["missing_fields"],
                )
        else:
            spec = requirement_clarifier.clarify(skill_request.text)
            output = requirement_blueprint_builder.build_blueprint_draft(spec).model_dump(mode="json")
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=output)

    def evidence_capability_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        skill_request = EvidenceSkillRequest(**request.inputs)
        if skill_request.operation == "list_signals":
            output = log_evidence.list_signals(limit=skill_request.limit).model_dump(mode="json")
        elif skill_request.operation == "list_promoted":
            output = log_evidence.list_promoted_evidence(limit=skill_request.limit).model_dump(mode="json")
        elif skill_request.operation == "list_index":
            output = log_evidence.list_index_entries(limit=skill_request.limit, app_instance_id=skill_request.app_instance_id or None).model_dump(mode="json")
        elif skill_request.operation == "context_summary":
            target_app = skill_request.app_instance_id or request.app_instance_id
            output = log_evidence.build_context_evidence_summary(target_app, limit=skill_request.limit or 3)
        elif skill_request.operation == "search_index":
            output = log_evidence.search_index(
                query=request.inputs.get("query", ""),
                app_instance_id=skill_request.app_instance_id or None,
                limit=skill_request.limit,
            ).model_dump(mode="json")
        else:
            output = log_evidence.get_stats_summary()
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=output)

    def context_compaction_capability_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        skill_request = ContextCompactionSkillRequest(**request.inputs)
        if skill_request.operation == "compact":
            output = context_compaction.compact(request.app_instance_id, reason=skill_request.reason).model_dump(mode="json")
        elif skill_request.operation == "working_set":
            output = context_compaction.build_working_set(request.app_instance_id).model_dump(mode="json")
        else:
            output = context_compaction.list_layers(request.app_instance_id)
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=output)

    def workflow_insight_capability_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        skill_request = WorkflowInsightSkillRequest(**request.inputs)
        if skill_request.operation == "overview":
            output = workflow_observability.get_overview(
                app_instance_id=request.app_instance_id,
                workflow_id=skill_request.workflow_id,
                failed_step_id=skill_request.failed_step_id,
            ).model_dump(mode="json")
        elif skill_request.operation == "timeline":
            output = workflow_observability.list_timeline_events(
                app_instance_id=request.app_instance_id,
                workflow_id=skill_request.workflow_id,
                limit=skill_request.limit,
            ).model_dump(mode="json")
        elif skill_request.operation == "dashboard":
            output = workflow_observability.get_dashboard_summary(
                app_instance_id=request.app_instance_id,
                workflow_id=skill_request.workflow_id,
                failed_step_id=skill_request.failed_step_id,
                recent_limit=skill_request.limit or 5,
            ).model_dump(mode="json")
        else:
            output = workflow_observability.get_stats_summary(
                app_instance_id=request.app_instance_id,
                workflow_id=skill_request.workflow_id,
            ).model_dump(mode="json")
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=output)

    def risk_governance_capability_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        skill_request = RiskGovernanceSkillRequest(**request.inputs)
        if skill_request.operation == "events":
            output = skill_risk_policy.get_event_page(
                skill_id=skill_request.skill_id or None,
                limit=skill_request.limit,
            ).model_dump(mode="json")
        elif skill_request.operation == "dashboard":
            output = skill_risk_policy.get_dashboard(recent_limit=skill_request.limit or 5).model_dump(mode="json")
        elif skill_request.operation == "approve_override":
            output = skill_risk_policy.approve_override(
                skill_id=skill_request.skill_id,
                reviewer=skill_request.reviewer,
                reason=skill_request.reason,
            ).model_dump(mode="json")
        elif skill_request.operation == "revoke_override":
            output = skill_risk_policy.revoke_override(
                skill_id=skill_request.skill_id,
                reviewer=skill_request.reviewer,
                reason=skill_request.reason,
            ).model_dump(mode="json")
        else:
            output = skill_risk_policy.get_stats_summary().model_dump(mode="json")
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=output)

    def prompt_selection_capability_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
        skill_request = PromptSelectionSkillRequest(**request.inputs)
        if skill_request.operation == "evidence_search":
            output = prompt_selection.search_evidence(
                query=skill_request.query,
                app_instance_id=skill_request.app_instance_id or request.app_instance_id,
                category=skill_request.category or None,
                limit=skill_request.limit or 5,
                strategy=skill_request.strategy,
            )
        else:
            output = prompt_selection.select_for_prompt(
                app_instance_id=skill_request.app_instance_id or request.app_instance_id,
                limit=skill_request.limit or 5,
                query=skill_request.query,
                category=skill_request.category or None,
                max_prompt_tokens=skill_request.max_prompt_tokens,
                reserved_output_tokens=skill_request.reserved_output_tokens,
                working_set_token_estimate=skill_request.working_set_token_estimate,
                per_evidence_token_estimate=skill_request.per_evidence_token_estimate,
                strategy=skill_request.strategy,
                include_prompt_assembly=skill_request.include_prompt_assembly,
            )
            if skill_request.operation == "model_ready_prompt":
                output = prompt_invocation.invoke_with_selection(
                    app_instance_id=skill_request.app_instance_id or request.app_instance_id,
                    query=skill_request.query,
                    category=skill_request.category or None,
                    limit=skill_request.limit or 5,
                    max_prompt_tokens=skill_request.max_prompt_tokens,
                    reserved_output_tokens=skill_request.reserved_output_tokens,
                    working_set_token_estimate=skill_request.working_set_token_estimate,
                    per_evidence_token_estimate=skill_request.per_evidence_token_estimate,
                    strategy=skill_request.strategy,
                    include_prompt_assembly=skill_request.include_prompt_assembly,
                )
        return SkillExecutionResult(skill_id=request.skill_id, status="completed", output=output)

    return {
        "skill.echo": demo_echo_skill,
        "system.app_config": system_app_config_skill,
        "system.state": system_state_skill,
        "system.audit": system_audit_skill,
        "system.context": system_context_skill,
        "model.responses.probe": model_responses_probe_skill,
        "requirement.skill": requirement_capability_skill,
        "evidence.skill": evidence_capability_skill,
        "context.compaction.skill": context_compaction_capability_skill,
        "workflow.insight.skill": workflow_insight_capability_skill,
        "risk.governance.skill": risk_governance_capability_skill,
        "prompt.selection.skill": prompt_selection_capability_skill,
    }


def bootstrap_builtin_skills(skill_runtime: SkillRuntimeService, services: dict[str, object]) -> None:
    skill_control = services["skill_control"]
    register_builtin_skills(skill_control)
    register_builtin_handlers(skill_runtime, build_builtin_skill_handlers(services), skill_control)
