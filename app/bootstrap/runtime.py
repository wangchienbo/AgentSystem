from __future__ import annotations

import os

from app.services.app_catalog import AppCatalogService
from app.services.system_skills.app_config import AppConfigService
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.app_refinement import AppRefinementService
from app.services.app_registry import AppRegistryService
from app.services.context_compaction import ContextCompactionService
from app.services.system_skills.context import ContextSkillService
from app.services.blueprint_validation import BlueprintValidationService
from app.services.skill_validation import SkillValidationService
from app.services.demonstration_extractor import DemonstrationExtractor
from app.services.event_bus import EventBusService
from app.services.evaluation_summary_service import EvaluationSummaryService
from app.services.experience_store import ExperienceStore
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.interaction_gateway import InteractionGateway
from app.services.lifecycle import AppLifecycleService
from app.services.model_self_refiner import ModelSelfRefiner
from app.services.model_skill_suggester import ModelSkillSuggester
from app.services.practice_review import PracticeReviewService
from app.services.priority_analysis import PriorityAnalysisService
from app.services.proposal_review import ProposalReviewService
from app.services.collection_policy_service import CollectionPolicyService
from app.services.policy_guard import PolicyGuardService
from app.services.log_evidence_service import LogEvidenceService
from app.services.requirement_router import RequirementRouter
from app.services.requirement_clarifier import RequirementClarifierService
from app.services.requirement_blueprint_builder import RequirementBlueprintBuilderService
from app.models.requirement_skill import RequirementSkillRequest
from app.models.evidence_skill import EvidenceSkillRequest
from app.models.context_compaction_skill import ContextCompactionSkillRequest
from app.models.workflow_insight_skill import WorkflowInsightSkillRequest
from app.models.risk_governance_skill import RiskGovernanceSkillRequest
from app.models.prompt_selection_skill import PromptSelectionSkillRequest
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.schema_registry import SchemaRegistryService
from app.services.self_refinement import SelfRefinementService
from app.services.refinement_loop import RefinementLoopService
from app.services.refinement_memory import RefinementMemoryStore
from app.services.refinement_rollout import RefinementRolloutService
from app.services.skill_control import SkillControlService
from app.services.skill_factory import SkillFactoryService
from app.services.skill_runtime import SkillRuntimeService
from app.services.skill_risk_policy import SkillRiskPolicyService
from app.services.prompt_selection_service import PromptSelectionService
from app.services.prompt_invocation_service import PromptInvocationService
from app.services.skill_suggestion import SkillSuggestionService
from app.services.supervisor import SupervisorService
from app.services.system_skills.state_audit import SystemAuditService, SystemStateService
from app.services.telemetry_service import TelemetryService
from app.services.upgrade_log_service import UpgradeLogService
from app.services.workflow_executor import WorkflowExecutorService
from app.services.workflow_observability import WorkflowObservabilityService
from app.services.workflow_subscription import WorkflowSubscriptionService


def build_runtime() -> dict[str, object]:
    router = RequirementRouter()
    requirement_clarifier = RequirementClarifierService(router=router)
    requirement_blueprint_builder = RequirementBlueprintBuilderService()
    skill_control = SkillControlService()
    schema_registry = SchemaRegistryService()
    schema_registry.register(
        "schema://system.app_config/input",
        {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["get", "set", "patch", "delete", "list"]},
                "key": {"type": "string"},
                "value": {},
                "config_schema": {"type": "object"},
                "working_set": {"type": "object"},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
    )
    schema_registry.register(
        "schema://system.app_config/output",
        {
            "type": "object",
            "properties": {
                "app_instance_id": {"type": "string"},
                "operation": {"type": "string"},
                "values": {"type": "object"},
                "key": {"type": "string"},
                "value": {},
                "history_count": {"type": "integer"},
            },
            "required": ["app_instance_id", "operation", "values", "key", "history_count"],
            "additionalProperties": True,
        },
    )
    schema_registry.register(
        "schema://system.app_config/error",
        {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
    )
    schema_registry.register(
        "schema://system.context/input",
        {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["get", "update", "append", "list_runtime_view"]},
                "current_goal": {"type": "string"},
                "current_stage": {"type": "string"},
                "status": {"type": "string"},
                "section": {"type": "string"},
                "key": {"type": "string"},
                "value": {},
                "tags": {"type": "array", "items": {"type": "string"}},
                "include_runtime": {"type": "boolean"},
                "working_set": {"type": "object"},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
    )
    schema_registry.register(
        "schema://system.context/output",
        {
            "type": "object",
            "properties": {
                "app_instance_id": {"type": "string"},
                "current_goal": {"type": "string"},
                "current_stage": {"type": "string"},
                "status": {"type": "string"},
                "entries": {"type": "array"},
                "context": {"type": "object"},
                "runtime": {},
            },
            "additionalProperties": True,
        },
    )
    schema_registry.register(
        "schema://system.context/error",
        {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
    )
    schema_registry.register(
        "schema://model.responses.probe/input",
        {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "working_set": {"type": "object"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    )
    schema_registry.register(
        "schema://model.responses.probe/output",
        {
            "type": "object",
            "properties": {
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "result": {"type": "object"},
            },
            "required": ["provider", "model", "result"],
            "additionalProperties": True,
        },
    )
    schema_registry.register(
        "schema://model.responses.probe/error",
        {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
    )
    schema_registry.register(
        "schema://requirement.skill/input",
        RequirementSkillRequest.model_json_schema(),
    )
    schema_registry.register(
        "schema://requirement.skill/output",
        {"type": "object", "additionalProperties": True},
    )
    schema_registry.register(
        "schema://requirement.skill/error",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    schema_registry.register(
        "schema://evidence.skill/input",
        EvidenceSkillRequest.model_json_schema(),
    )
    schema_registry.register(
        "schema://evidence.skill/output",
        {"type": "object", "additionalProperties": True},
    )
    schema_registry.register(
        "schema://evidence.skill/error",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    schema_registry.register(
        "schema://context.compaction.skill/input",
        ContextCompactionSkillRequest.model_json_schema(),
    )
    schema_registry.register(
        "schema://context.compaction.skill/output",
        {"type": "object", "additionalProperties": True},
    )
    schema_registry.register(
        "schema://context.compaction.skill/error",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    schema_registry.register(
        "schema://workflow.insight.skill/input",
        WorkflowInsightSkillRequest.model_json_schema(),
    )
    schema_registry.register(
        "schema://workflow.insight.skill/output",
        {"type": "object", "additionalProperties": True},
    )
    schema_registry.register(
        "schema://workflow.insight.skill/error",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    schema_registry.register(
        "schema://risk.governance.skill/input",
        RiskGovernanceSkillRequest.model_json_schema(),
    )
    schema_registry.register(
        "schema://risk.governance.skill/output",
        {"type": "object", "additionalProperties": True},
    )
    schema_registry.register(
        "schema://risk.governance.skill/error",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    schema_registry.register(
        "schema://prompt.selection.skill/input",
        PromptSelectionSkillRequest.model_json_schema(),
    )
    schema_registry.register(
        "schema://prompt.selection.skill/output",
        {"type": "object", "additionalProperties": True},
    )
    schema_registry.register(
        "schema://prompt.selection.skill/error",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    skill_validation = SkillValidationService(skill_control=skill_control, schema_registry=schema_registry)
    blueprint_validation = BlueprintValidationService(skill_validation=skill_validation)
    app_profile_resolver = AppProfileResolverService(skill_control=skill_control)
    experience_store = ExperienceStore()
    demonstration_extractor = DemonstrationExtractor()
    runtime_store = RuntimeStateStore()
    app_data_store = AppDataStore(store=runtime_store)
    app_data_store.ensure_skill_asset_namespace()
    app_config_service = AppConfigService(data_store=app_data_store, store=runtime_store)
    system_state_service = SystemStateService(data_store=app_data_store, store=runtime_store)
    system_audit_service = SystemAuditService(data_store=app_data_store, store=runtime_store)
    lifecycle = AppLifecycleService(store=runtime_store)
    runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=runtime_store)
    app_context_store = AppContextStore(lifecycle=lifecycle, store=runtime_store, runtime_host=runtime_host)
    scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime_host, store=runtime_store)
    event_bus = EventBusService(scheduler=scheduler, store=runtime_store)
    supervisor = SupervisorService(runtime_host=runtime_host, store=runtime_store)
    context_skill_service = ContextSkillService(context_store=app_context_store)
    collection_policy_service = CollectionPolicyService(store=runtime_store)
    upgrade_log_service = UpgradeLogService()
    log_evidence = LogEvidenceService(store=runtime_store)
    telemetry_service = TelemetryService(
        store=runtime_store,
        policy_service=collection_policy_service,
        upgrade_log_service=upgrade_log_service,
    )
    evaluation_summary_service = EvaluationSummaryService(
        store=runtime_store,
        upgrade_log_service=upgrade_log_service,
    )
    practice_review = PracticeReviewService(
        event_bus=event_bus,
        data_store=app_data_store,
        experience_store=experience_store,
        context_store=app_context_store,
    )
    skill_risk_policy = SkillRiskPolicyService(store=runtime_store, log_evidence_service=log_evidence)
    model_skill_suggester = ModelSkillSuggester()
    skill_suggestion = SkillSuggestionService(
        experience_store=experience_store,
        model_suggester=model_skill_suggester,
        risk_policy=skill_risk_policy,
    )
    app_registry = AppRegistryService(store=runtime_store)
    model_self_refiner = ModelSelfRefiner() if os.getenv("AGENTSYSTEM_ENABLE_MODEL_REFINER") == "1" else None
    self_refinement = SelfRefinementService(
        experience_store=experience_store,
        registry=app_registry,
        lifecycle=lifecycle,
        model_self_refiner=model_self_refiner,
        context_store=app_context_store,
    )
    proposal_review = ProposalReviewService(
        lifecycle=lifecycle,
        store=runtime_store,
        context_store=app_context_store,
    )
    priority_analysis = PriorityAnalysisService(
        proposal_review=proposal_review,
        context_store=app_context_store,
    )
    refinement_memory = RefinementMemoryStore(store=runtime_store)
    refinement_loop = RefinementLoopService(
        proposal_review=proposal_review,
        priority_analysis=priority_analysis,
        memory=refinement_memory,
    )
    refinement_rollout = RefinementRolloutService(
        memory=refinement_memory,
        proposal_review=proposal_review,
    )
    app_installer = AppInstallerService(
        registry=app_registry,
        lifecycle=lifecycle,
        runtime_host=runtime_host,
        data_store=app_data_store,
        context_store=app_context_store,
        app_config_service=app_config_service,
        app_profile_resolver=app_profile_resolver,
        blueprint_validation=blueprint_validation,
    )
    app_catalog = AppCatalogService()
    skill_runtime = SkillRuntimeService(
        store=runtime_store,
        schema_registry=schema_registry,
        telemetry_service=telemetry_service,
    )
    generated_skill_assets = GeneratedSkillAssetStore(app_data_store)
    skill_factory = SkillFactoryService(
        skill_control=skill_control,
        skill_runtime=skill_runtime,
        schema_registry=schema_registry,
        generated_assets=generated_skill_assets,
        risk_policy=skill_risk_policy,
    )
    policy_guard = PolicyGuardService()
    app_refinement = AppRefinementService(
        experience_store=experience_store,
        skill_control=skill_control,
        skill_factory=skill_factory,
    )
    workflow_executor = WorkflowExecutorService(
        registry=app_registry,
        lifecycle=lifecycle,
        data_store=app_data_store,
        event_bus=event_bus,
        context_store=app_context_store,
        skill_runtime=skill_runtime,
        store=runtime_store,
        telemetry_service=telemetry_service,
        policy_guard=policy_guard,
        log_evidence_service=log_evidence,
        prompt_invocation_service=None,
    )
    workflow_executor._skill_risk_policy = skill_risk_policy
    workflow_subscription = WorkflowSubscriptionService(
        workflow_executor=workflow_executor,
        store=runtime_store,
    )
    workflow_observability = WorkflowObservabilityService(workflow_executor=workflow_executor)
    context_compaction = ContextCompactionService(
        app_context_store=app_context_store,
        workflow_executor=workflow_executor,
        store=runtime_store,
        log_evidence_service=log_evidence,
    )
    workflow_executor._context_compaction = context_compaction
    prompt_selection = PromptSelectionService(context_compaction=context_compaction, log_evidence=log_evidence)
    prompt_invocation = PromptInvocationService(
        prompt_selection=prompt_selection,
        telemetry_service=telemetry_service,
        evaluation_summary_service=evaluation_summary_service,
        skill_risk_policy_service=skill_risk_policy,
    )
    workflow_executor._prompt_invocation_service = prompt_invocation
    interaction_gateway = InteractionGateway(
        catalog=app_catalog,
        router=router,
        lifecycle=lifecycle,
        runtime_host=runtime_host,
        installer=app_installer,
        context_store=app_context_store,
        telemetry_service=telemetry_service,
    )
    skill_factory.reload_generated_skills()

    return locals()
