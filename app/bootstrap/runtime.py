from __future__ import annotations

import logging
import os

from app.services.app_catalog import AppCatalogService
from app.services.system_skills.app_config import AppConfigService
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.app_refinement import AppRefinementService
from app.services.app_refinement_orchestrator import AppRefinementOrchestratorService
from app.services.app_registry import AppRegistryService
from app.services.context_compaction import ContextCompactionService
from app.services.system_skills.context import ContextSkillService
from app.services.blueprint_validation import BlueprintValidationService
from app.services.skill_validation import SkillValidationService
from app.services.demonstration_extractor import DemonstrationExtractor
from app.services.event_bus import EventBusService
from app.services.evaluation_summary_service import EvaluationSummaryService
from app.services.experience_store import ExperienceStore
from app.services.feedback_service import FeedbackService
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.interaction_gateway import InteractionGateway
from app.services.lifecycle import AppLifecycleService
from app.services.model_self_refiner import ModelSelfRefiner
from app.services.model_skill_suggester import ModelSkillSuggester
from app.services.practice_review import PracticeReviewService
from app.services.priority_analysis import PriorityAnalysisService
from app.services.proposal_review import ProposalReviewService
from app.services.collection_policy_service import CollectionPolicyService
from app.services.context_retrieval_service import ContextRetrievalService
from app.services.persistence_health_service import PersistenceHealthService
from app.services.policy_authority_service import PolicyAuthorityService
from app.governance.audit_logger import AuditLogger
from app.governance.cost_quota import CostQuotaManager
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
from app.services.persistence_service import PersistenceService
from app.services.blueprint_compare import BlueprintCompareService
from app.services.upgrade_service import UpgradeService
from app.services.rollback_service import RollbackService
from app.services.workflow_executor import WorkflowExecutorService
from app.services.workflow_observability import WorkflowObservabilityService
from app.services.workflow_subscription import WorkflowSubscriptionService
from app.services.meta_app.bootstrap import MetaAppBootstrapService
from app.services.meta_app.orchestrator import MetaAppCreationOrchestrator
from app.models.maoxuan_skill import MaoxuanSkillRequest
from app.models.memory_skill import MemorySkillRequest
from app.services.system_skills.maoxuan import MaoxuanSkillService
from app.services.system_skills.memory import MemorySkillService
from app.services.interactive_app import InteractiveAppService
from app.services.interactive_app_workflow import InteractiveAppWorkflow
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.services.session_router import SessionRouter
from app.services.pipeline_service import PipelineService
from app.system.gateway.tool_calling_interpreter import ToolCallingInterpreter
from app.services.hot_tool_manager import HotToolManager, FIXED_TOOLS
from app.tools.internal_tools import AGENTSYSTEM_INTERNAL_TOOL_HANDLERS

# ── G.1/G.2: MessageBus, Workers, LogCenter, SkillMeta, PathStore ─────
from app.core.message_bus import MessageBus
from app.core.worker_manager import WorkerManager
from app.core.gateway_orchestrator_bridge import GatewayOrchestratorBridge
from app.services.log_center import LogCenter
from app.services.skill_meta_service import SkillMetaService
from app.services.path_store import PathStore
from app.models.log_center import LogCollectionConfig


def build_runtime(*, runtime_store_base_dir: str | None = None, app_data_base_dir: str | None = None) -> dict[str, object]:
    router = RequirementRouter()
    requirement_clarifier = RequirementClarifierService(router=router)
    requirement_blueprint_builder = RequirementBlueprintBuilderService()
    skill_control = SkillControlService()
    schema_registry = SchemaRegistryService()

    # Config Center — system-level skill template + app binding config
    from app.services.config_center import ConfigCenterService
    config_center = ConfigCenterService()

    # Phase F.1: Unified Model Router
    from app.services.model_router import ModelRouter
    from app.services.tool_calling_engine import ToolCallingEngine
    model_router = ModelRouter(skill_control=skill_control, config_center=config_center)
    tool_calling_engine = ToolCallingEngine(model_router=model_router)
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
    schema_registry.register(
        "schema://system.maoxuan/input",
        MaoxuanSkillRequest.model_json_schema(),
    )
    schema_registry.register(
        "schema://system.maoxuan/output",
        {"type": "object", "additionalProperties": True},
    )
    schema_registry.register(
        "schema://system.maoxuan/error",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    schema_registry.register(
        "schema://system.memory/input",
        MemorySkillRequest.model_json_schema(),
    )
    schema_registry.register(
        "schema://system.memory/output",
        {"type": "object", "additionalProperties": True},
    )
    schema_registry.register(
        "schema://system.memory/error",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    skill_validation = SkillValidationService(skill_control=skill_control, schema_registry=schema_registry)
    blueprint_validation = BlueprintValidationService(skill_validation=skill_validation)
    app_profile_resolver = AppProfileResolverService(skill_control=skill_control)
    experience_store = ExperienceStore()
    demonstration_extractor = DemonstrationExtractor()
    runtime_store = RuntimeStateStore(base_dir=runtime_store_base_dir or "data/runtime")
    app_data_store = AppDataStore(base_dir=app_data_base_dir or "data/namespaces", store=runtime_store)
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
    policy_authority = PolicyAuthorityService(store=runtime_store)
    # Phase I Governance services
    audit_logger = AuditLogger()
    cost_quota_manager = CostQuotaManager()
    persistence_health = PersistenceHealthService(store=runtime_store)
    upgrade_log_service = UpgradeLogService()
    blueprint_compare = BlueprintCompareService()
    upgrade_service = UpgradeService(
        lifecycle=lifecycle,
        log_service=upgrade_log_service,
        compare_service=blueprint_compare,
        runtime_center=None,  # Will be set after Phase N initialization
        asset_center=None,  # Will be set after Phase N initialization
    )
    rollback_service = RollbackService(
        upgrade_service=upgrade_service,
        log_service=upgrade_log_service,
    )
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
    model_skill_suggester = ModelSkillSuggester(model_router=model_router)
    skill_suggestion = SkillSuggestionService(
        experience_store=experience_store,
        model_suggester=model_skill_suggester,
        risk_policy=skill_risk_policy,
    )
    app_registry = AppRegistryService(store=runtime_store)
    model_self_refiner = ModelSelfRefiner(model_router=model_router) if os.getenv("AGENTSYSTEM_ENABLE_MODEL_REFINER") == "1" else None
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
        config_center=config_center,
        asset_center=None,  # Will be set after Phase N initialization
        runtime_center=None,  # Will be set after Phase N initialization
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
    context_retrieval = ContextRetrievalService(app_context_store=app_context_store, context_compaction=context_compaction)
    prompt_selection = PromptSelectionService(context_compaction=context_compaction, log_evidence=log_evidence)
    prompt_invocation = PromptInvocationService(
        prompt_selection=prompt_selection,
        model_router=model_router,
        telemetry_service=telemetry_service,
        evaluation_summary_service=evaluation_summary_service,
        skill_risk_policy_service=skill_risk_policy,
    )
    workflow_executor._prompt_invocation_service = prompt_invocation
    app_refinement_orchestrator = AppRefinementOrchestratorService(
        app_refinement=app_refinement,
        app_registry=app_registry,
        app_installer=app_installer,
        workflow_executor=workflow_executor,
        policy_authority=policy_authority,
    )
    interaction_gateway = InteractionGateway(
        catalog=app_catalog,
        router=router,
        lifecycle=lifecycle,
        runtime_host=runtime_host,
        installer=app_installer,
        context_store=app_context_store,
        telemetry_service=telemetry_service,
    )

    # Phase N asset infrastructure must be initialized before MetaApp orchestrator wiring.
    from app.services.system_catalog import SystemCatalog, CatalogEntry
    from app.services.asset_center import AssetCenter
    from app.services.runtime_center import RuntimeCenter
    from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    system_catalog = SystemCatalog()
    asset_center = AssetCenter(
        source_dir=os.path.join(_project_root, "source"),
        installed_dir=os.path.join(_project_root, "installed"),
        build_dir=os.path.join(_project_root, "build"),
        data_dir=os.path.join(_project_root, "data"),
    )
    runtime_center = RuntimeCenter(data_file=os.path.join(_project_root, "data", "runtime_center.json"))
    asset_center.discover()

    def _register_core_runtime_assets() -> None:
        core_assets = [
            ("asset:master_control:v1", "master_control", "Central execution and worker governance", master_control, [
                AssetCapability(name="dispatch worker action", description="Dispatch a worker action through master control", method="dispatch", side_effect_level="admin", permission_hint="admin"),
            ]),
            ("asset:config_center:v1", "config_center", "Bootstrap configuration source", config_center, [
                AssetCapability(name="get config", description="Read config center values", method="get_config", side_effect_level="read"),
            ]),
            ("asset:runtime_center:v1", "runtime_center", "Runtime source of truth for live assets", runtime_center, [
                AssetCapability(name="list assets", description="List runtime assets", method="list_assets", side_effect_level="read"),
                AssetCapability(name="query asset info", description="Query one runtime asset", method="query_asset_info", side_effect_level="read"),
                AssetCapability(name="call asset method", description="Call a runtime asset capability through mapped entry", method="call_asset_method", side_effect_level="write", permission_hint="admin"),
            ]),
            ("asset:model_router:v1", "model_router", "Model routing and selection", model_router, [
                AssetCapability(name="resolve model", description="Resolve effective model for a caller", method="resolve_model", side_effect_level="read"),
            ]),
            ("asset:tool_calling_engine:v1", "tool_calling_engine", "LLM tool execution layer", tool_calling_engine, [
                AssetCapability(name="run tool call", description="Run a structured tool call turn", method="run_tool_call", side_effect_level="write"),
            ]),
            ("asset:app_management_worker:v1", "app_management_worker", "App lifecycle and runtime worker", app_mgmt_worker, [
                AssetCapability(name="list apps", description="List registered apps", method="list_apps", side_effect_level="read"),
                AssetCapability(name="query app", description="Query one app record", method="query_app", side_effect_level="read"),
                AssetCapability(name="start app", description="Start an app instance", method="start_app", side_effect_level="write"),
                AssetCapability(name="stop app", description="Stop an app instance", method="stop_app", side_effect_level="write"),
                AssetCapability(name="delete app", description="Delete an app instance", method="delete_app", side_effect_level="write"),
                AssetCapability(name="uninstall app", description="Uninstall an app instance", method="uninstall_app", side_effect_level="write"),
            ]),
            ("asset:user_manager:v1", "user_manager", "User and permission worker", user_manager, [
                AssetCapability(name="list users", description="List known users", method="list_users", side_effect_level="read"),
                AssetCapability(name="show permissions", description="Show user permissions", method="show_permissions", side_effect_level="read"),
            ]),
            ("asset:refinement_worker:v1", "refinement_worker", "App refinement worker", refinement_worker_m, [
                AssetCapability(name="refine app", description="Refine an app with a modification request", method="refine_app", side_effect_level="write"),
            ]),
            ("asset:package_manager:v1", "package_manager", "Package and asset installation manager", package_manager_executor, [
                AssetCapability(name="list installed packages", description="List installed runtime packages", method="package_list_installed", side_effect_level="read"),
                AssetCapability(name="search packages", description="Search source packages", method="package_search", side_effect_level="read"),
                AssetCapability(name="build package", description="Build a source package", method="package_build", side_effect_level="write"),
                AssetCapability(name="install package", description="Install a built package", method="package_install", side_effect_level="write"),
                AssetCapability(name="uninstall package", description="Uninstall an installed package", method="package_uninstall", side_effect_level="write"),
                AssetCapability(name="rollback package", description="Rollback a package to a target version", method="package_rollback", side_effect_level="write"),
            ]),
        ]
        method_map_by_name = {
            "master_control": {
                "dispatch": lambda operation="query_status", target="", params=None, user_id="system", user_role="system": master_control.execute(operation=operation, user_id=user_id, user_role=user_role, target=target, params=params or {}),
            },
            "config_center": {
                "get_config": lambda skill_id=None, app_id=None: {
                    "skill_config": (lambda cfg: cfg.__dict__ if cfg is not None else None)(config_center.get_skill_config(skill_id) if skill_id else None),
                    "app_bindings": [b.__dict__ for b in config_center.get_app_bindings(app_id)] if app_id else [],
                },
            },
            "runtime_center": {
                "list_assets": lambda filter_text=None: [a.model_dump(mode="json") for a in runtime_center.list_assets() if not filter_text or filter_text.lower() in json.dumps(a.model_dump(mode="json"), ensure_ascii=False).lower()],
                "query_asset_info": lambda asset_id: runtime_center.query_asset_info(asset_id),
                "call_asset_method": lambda asset_id, method, params=None: runtime_center.call_asset_method(asset_id=asset_id, method=method, params=params or {}),
            },
            "model_router": {
                "resolve_model": lambda caller="system", complexity="moderate": model_router.resolve(caller, complexity).__dict__,
            },
            "tool_calling_engine": {
                "run_tool_call": lambda **kwargs: {
                    "accepted": True,
                    "note": "Tool call execution mapping placeholder, requires full request payload",
                    "received": kwargs,
                },
            },
            "app_management_worker": {
                "create_app": lambda app_name, config=None: app_mgmt_worker.execute("create_app", app_name, {"config": config or {}}),
                "modify_app": lambda app_name, modification: app_mgmt_worker.execute("modify_app", app_name, {"modification": modification}),
                "list_apps": lambda status="all": app_mgmt_worker.execute("list_apps", "", {"status": status}),
                "query_app": lambda app_name: app_mgmt_worker.execute("query_app", app_name, {}),
                "start_app": lambda app_name: app_mgmt_worker.execute("start_app", app_name, {}),
                "stop_app": lambda app_name: app_mgmt_worker.execute("stop_app", app_name, {}),
                "delete_app": lambda app_name: app_mgmt_worker.execute("delete_app", app_name, {}),
                "uninstall_app": lambda app_name: app_mgmt_worker.execute("uninstall_app", app_name, {}),
            },
            "user_manager": {
                "list_users": lambda: user_manager.execute("list_users", "", {}),
                "show_permissions": lambda target_user="": user_manager.execute("show_permissions", target_user, {"target_user": target_user}),
            },
            "refinement_worker": {
                "refine_app": lambda app_name, modification, target_app=None, context_hints=None, related_session_ids=None: refinement_worker_m.execute(
                    "refine_app",
                    app_name,
                    {
                        "modification": modification,
                        "target_app": target_app or app_name,
                        "context_hints": context_hints or [],
                        "related_session_ids": related_session_ids or [],
                    },
                ),
            },
            "package_manager": {
                "package_list_installed": lambda asset_type=None: package_manager_executor.execute("package_list_installed", {"asset_type": asset_type}).data,
                "package_search": lambda query: package_manager_executor.execute("package_search", {"query": query}).data,
                "package_build": lambda asset_id: package_manager_executor.execute("package_build", {"asset_id": asset_id}).data,
                "package_install": lambda asset_id, build_hash=None: package_manager_executor.execute("package_install", {"asset_id": asset_id, "build_hash": build_hash}).data,
                "package_uninstall": lambda asset_id: package_manager_executor.execute("package_uninstall", {"asset_id": asset_id}).data,
                "package_rollback": lambda asset_id, target_version: package_manager_executor.execute("package_rollback", {"asset_id": asset_id, "target_version": target_version}).data,
            },
            "light_brain_gateway": {
                "list_assets": lambda filter="": asset_tool_executor.execute("list_assets", {"filter": filter}, "system").data,
                "query_asset_info": lambda asset_id: asset_tool_executor.execute("query_asset_info", {"asset_id": asset_id}, "system").data,
                "call_asset_method": lambda asset_id, method, params=None: asset_tool_executor.execute("call_asset_method", {"asset_id": asset_id, "method": method, "params": params or {}}, "system").data,
            },
        }
        for asset_id, name, description, service, capabilities in core_assets:
            runtime_center.register_asset(
                AssetDescriptor(
                    asset_id=asset_id,
                    asset_type=AssetType.SERVICE,
                    asset_kind=AssetKind.CORE_RUNTIME,
                    version="1.0.0",
                    owner_type="system",
                    owner_id="system",
                    source_of_truth="runtime",
                    status=AssetState.ACTIVE,
                    capabilities=capabilities,
                    invoke_contract={"kind": "service", "service_name": name},
                    health_contract={"heartbeat": False},
                    name=name,
                    description=description,
                    tags=["phase-h", "core-runtime"],
                    metadata={"python_type": type(service).__name__},
                ),
                service_ref=service,
                method_mappings=method_map_by_name.get(name, {}),
            )


    # Wire Phase N assets into services created earlier (couldn't reference these at creation time)
    app_installer._asset_center = asset_center
    app_installer._runtime_center = runtime_center
    upgrade_service._runtime_center = runtime_center
    upgrade_service._asset_center = asset_center

    meta_app_bootstrap = MetaAppBootstrapService(model_router=model_router)
    meta_app_orchestrator = MetaAppCreationOrchestrator(
        meta_app_bootstrap=meta_app_bootstrap,
        skill_factory=skill_factory,
        lifecycle=lifecycle,
        runtime_host=runtime_host,
        app_registry=app_registry,
        asset_center=asset_center,
        system_catalog=system_catalog,
    )

    # Phase F.3: App Designer (Path B) — LLM-driven app creation with skill composition
    from app.services.app_designer.intent_analyzer import AppIntentAnalyzer
    from app.services.app_designer.architect import AppArchitect
    from app.services.app_designer.orchestrator import AppDesignOrchestrator
    app_intent_analyzer = AppIntentAnalyzer(model_router=model_router)
    app_architect = AppArchitect(model_router=model_router, skill_registry=skill_factory)
    app_design_orchestrator = AppDesignOrchestrator(
        intent_analyzer=app_intent_analyzer,
        architect=app_architect,
        skill_factory=skill_factory,
    )
    maoxuan_service = MaoxuanSkillService(model_router=model_router)
    memory_skill_service = MemorySkillService()
    user_service = UserService()
    interactive_app = InteractiveAppService()
    interactive_app_workflow = InteractiveAppWorkflow(
        interactive_app=interactive_app,
        memory_service=memory_skill_service,
        llm_responder=None,  # Will be set after llm_responder is created
    )
    persistence_service = PersistenceService()
    feedback_service = FeedbackService(store=runtime_store)
    skill_factory.reload_generated_skills()

    # -- Permission Skill (through main controller) ----------------------------
    from app.services.system_skills.permission import PermissionSkillService
    permission_skill = PermissionSkillService(user_service=user_service)

    # -- G.1/G.2: MessageBus + Workers + LogCenter + SkillMeta + PathStore ---
    g1g2_bus = MessageBus()
    g1g2_worker_manager = WorkerManager(message_bus=g1g2_bus)
    g1g2_log_center = LogCenter()
    g1g2_meta_service = SkillMetaService()
    # Use absolute path for PathStore so it finds YAML definitions reliably
    # __file__ = app/bootstrap/runtime.py, go up 3 levels to get AgentSystem project root
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    g1g2_path_store = PathStore(paths_dir=os.path.join(_project_root, "data", "paths"))
    # Pre-load path definitions from YAML files
    g1g2_path_store.load_all()
    # -- Dynamic Path Composer --------------------------------------------------
    from app.services.dynamic_path_composer import DynamicPathComposer
    g1g2_dynamic_composer = DynamicPathComposer(
        skill_meta_service=g1g2_meta_service,
        message_bus=g1g2_bus,
        model_router=model_router,
        universal_skill=None,  # Orchestrator handles universal fallback
    )
    g1g2_bridge = GatewayOrchestratorBridge(
        bus=g1g2_bus,
        worker_manager=g1g2_worker_manager,
        log_center=g1g2_log_center,
        meta_service=g1g2_meta_service,
        path_store=g1g2_path_store,
        dynamic_composer=g1g2_dynamic_composer,
    )

    # -- Dynamic Path Composer (dynamic skill chain composition) ---------------
    from app.services.dynamic_path_composer import DynamicPathComposer
    g1g2_dynamic_composer = DynamicPathComposer(
        skill_meta_service=g1g2_meta_service,
        message_bus=g1g2_bus,
        model_router=model_router,
        universal_skill=None,  # Will be wired after universal skill is available
    )
    logger = logging.getLogger(__name__)
    logger.info(
        "G.1/G.2 modules instantiated: bus=%s, workers=%s, log=%s, meta=%s, paths=%s, bridge=%s",
        type(g1g2_bus).__name__, type(g1g2_worker_manager).__name__,
        type(g1g2_log_center).__name__, type(g1g2_meta_service).__name__,
        type(g1g2_path_store).__name__, type(g1g2_bridge).__name__,
    )

    # -- LightBrain interaction gateway -----------------------------------------
    from app.services.light_brain_gateway import LightBrainGateway
    from app.services.light_brain_interpreter import LightBrainInterpreter
    from app.services.light_brain_memory import LightBrainMemory
    from app.services.llm_responder import LLMResponder
    from app.services.external_model_review import ExternalModelReviewService, ExternalModelReviewWorker
    from app.services.tool_registry import ToolRegistry, ToolDefinition, ToolParameter
    from app.services.asset_tools import AssetToolExecutor, make_all_asset_tools
    from app.services.package_manager import PackageManagerExecutor, make_all_package_tools

    # External model review (planned but not yet implemented)
    external_model_review = ExternalModelReviewService(model_router=None)

    logger.info("System catalog loaded: %d entries", system_catalog.count())

    # Asset tool executor — bridges LLM tool calls to runtime asset registry
    asset_tool_executor = AssetToolExecutor(registry=runtime_center, schema_registry=schema_registry)

    package_manager_executor = PackageManagerExecutor(asset_center=asset_center)
    app_installer._asset_center = asset_center
    logger.info(
        "Asset Center initialized: %d assets in source/, %d installed",
        len(asset_center.list_assets()),
        len(asset_center.list_installed()),
    )

    # Tool registry
    tool_registry = ToolRegistry()

    # -- Phase M: Master Control + subordinate Workers -----------------------
    from app.services.master_control import MasterControl
    from app.services.workers.app_management_worker import AppManagementWorker
    from app.services.workers.user_manager import UserManager
    from app.services.workers.skill_manager import SkillManager
    from app.services.workers.refinement_worker import RefinementWorker
    from app.services.workers.file_worker import FileWorker
    from app.services.workers.suggestion_worker import SuggestionWorker

    master_control = MasterControl()
    master_control.set_tool_registry(tool_registry)
    master_control.set_permission_service(permission_skill)

    # Create subordinate workers
    app_mgmt_worker = AppManagementWorker(
        app_registry=app_registry,
        lifecycle=lifecycle,
        app_installer=app_installer,
        app_catalog=app_catalog,
        tool_registry=tool_registry,
        runtime_center=runtime_center,
        audit_logger=audit_logger,
        cost_quota_manager=cost_quota_manager,
        policy_authority_service=policy_authority,
    )
    user_manager = UserManager(
        user_service=user_service,
        permission_service=permission_skill,
    )
    skill_manager = SkillManager(
        skill_registry=skill_factory,
        skill_meta_service=g1g2_meta_service,
    )
    refinement_worker_m = RefinementWorker(
        refinement_orchestrator=app_refinement_orchestrator,
        app_registry=app_registry,
    )
    file_worker = FileWorker(persistence=persistence_service)
    suggestion_worker_m = SuggestionWorker()
    external_review_worker = ExternalModelReviewWorker(external_model_review)

    # Register workers into MasterControl
    master_control.register_worker("app_management", app_mgmt_worker)
    master_control.register_worker("user_manager", user_manager)
    master_control.register_worker("skill_manager", skill_manager)
    master_control.register_worker("refinement", refinement_worker_m)
    master_control.register_worker("file_worker", file_worker)
    master_control.register_worker("suggestion", suggestion_worker_m)
    master_control.register_worker("external_review", external_review_worker)
    master_control.register_worker("package_manager", package_manager_executor)
    logger.info("Phase M: MasterControl + %d subordinate Workers registered", 8)

    # Register asset tools into the tool registry
    for tool_def in make_all_asset_tools():
        tool_registry.register(ToolDefinition(
            name=tool_def.name,
            description=tool_def.description,
            parameters=[ToolParameter(name=p.name, type=p.type, description=p.description, required=p.required) for p in tool_def.parameters],
            category="asset",
        ))

    # Register asset tool handlers with ToolCallingEngine
    def _query_asset_detail_handler(asset_id: str) -> dict:
        """Handler for query_asset_detail tool."""
        result = asset_tool_executor.execute("query_asset_detail", {"asset_id": asset_id}, "system")
        return {"success": result.success, "data": result.data, "error": result.error}

    def _list_assets_handler(filter: str | None = None) -> dict:
        """Handler for list_assets tool."""
        result = asset_tool_executor.execute("list_assets", {"filter": filter or ""}, "system")
        return {"success": result.success, "data": result.data, "error": result.error}

    def _query_asset_info_handler(asset_id: str) -> dict:
        """Handler for query_asset_info tool."""
        result = asset_tool_executor.execute("query_asset_info", {"asset_id": asset_id}, "system")
        return {"success": result.success, "data": result.data, "error": result.error}

    def _call_asset_method_handler(asset_id: str, method: str, params: dict | None = None) -> dict:
        """Handler for call_asset_method tool."""
        result = asset_tool_executor.execute(
            "call_asset_method",
            {"asset_id": asset_id, "method": method, "params": params or {}},
            "system"
        )
        return {"success": result.success, "data": result.data, "error": result.error}

    tool_calling_engine.register_tool("query_asset_detail", _query_asset_detail_handler)
    tool_calling_engine.register_tool("list_assets", _list_assets_handler)
    tool_calling_engine.register_tool("query_asset_info", _query_asset_info_handler)
    tool_calling_engine.register_tool("call_asset_method", _call_asset_method_handler)

    # Register package management tools (source/ installed/ separation)
    for tool_def in make_all_package_tools():
        tool_registry.register(ToolDefinition(
            name=tool_def.name,
            description=tool_def.description,
            parameters=[ToolParameter(name=p.name, type=p.type, description=p.description, required=p.required) for p in tool_def.parameters],
            category="package_manager",
        ))

    tool_registry.register(ToolDefinition(
        name="external_review_plan",
        description="调用受控外模型层进行方案评审",
        parameters=[
            ToolParameter(name="prompt", type="string", description="待评审方案", required=True),
            ToolParameter(name="context", type="object", description="补充上下文", required=False),
        ],
        category="external_review",
    ))
    tool_registry.register(ToolDefinition(
        name="external_review_code",
        description="调用受控外模型层进行代码评审",
        parameters=[
            ToolParameter(name="prompt", type="string", description="待评审代码或变更说明", required=True),
            ToolParameter(name="context", type="object", description="补充上下文", required=False),
        ],
        category="external_review",
    ))

    for name, description, params in [
        ("start_asset", "启动一个已安装资产", [ToolParameter(name="asset_id", type="string", description="资产ID", required=True)]),
        ("stop_asset", "停止一个运行中资产", [ToolParameter(name="asset_id", type="string", description="资产ID", required=True)]),
        ("health_check_asset", "查询资产运行健康状态", [ToolParameter(name="asset_id", type="string", description="资产ID", required=True)]),
    ]:
        tool_registry.register(ToolDefinition(name=name, description=description, parameters=params, category="app_management"))

    # Asset self-registration hooks — injected into lifecycle
    def _on_asset_start(app_instance_id: str) -> None:
        """Register runtime-only state when an asset starts running."""
        try:
            instance = lifecycle.get_instance(app_instance_id)
            asset_id = f"app.{instance.id}"
            owner_id = f"user.{instance.owner_user_id}" if instance.owner_user_id != "system" else "system"
            if instance is not None:
                runtime_center.register(
                    asset_id=asset_id,
                    version=getattr(instance, "installed_version", "0.0.0") or "0.0.0",
                    pid=0,
                    endpoint="",
                    owner=owner_id,
                    status="running",
                )
            logger.info("Runtime self-registered: %s", asset_id)
        except Exception as e:
            logger.warning("Asset start hook failed for %s: %s", app_instance_id, e)

    def _on_asset_stop(app_instance_id: str) -> None:
        """Unregister runtime-only state when an asset stops."""
        try:
            runtime_center.unregister(f"app.{app_instance_id}")
            logger.info("Runtime unregistered: app.%s", app_instance_id)
        except Exception as e:
            logger.warning("Asset stop hook failed for %s: %s", app_instance_id, e)

    lifecycle.set_asset_hooks(on_asset_start=_on_asset_start, on_asset_stop=_on_asset_stop)

    light_brain_memory = LightBrainMemory()
    light_brain_interpreter = LightBrainInterpreter()
    llm_responder = LLMResponder(model_router=model_router)
    external_model_review = ExternalModelReviewService(model_router=model_router)
    # Register core runtime assets after core services exist
    _register_core_runtime_assets()

    # Initialize HotToolManager and register discoverable tool metadata
    hot_tool_manager = HotToolManager()
    for tool_name, handler in AGENTSYSTEM_INTERNAL_TOOL_HANDLERS.items():
        tool_calling_engine.register_tool(tool_name, handler)

    for tool_def in FIXED_TOOLS:
        hot_tool_manager.register_tool(tool_def, fixed=True)

    # Register asset-tool metadata for discovery, but do not materialize
    # capability-level dynamic tool names from runtime assets.
    for tool_def in make_all_asset_tools():
        hot_tool_manager.register_tool({
            "name": tool_def.name,
            "description": tool_def.description,
            "parameters": {
                "type": "object",
                "properties": {
                    p.name: {"type": p.type, "description": p.description}
                    for p in tool_def.parameters
                },
                "required": [p.name for p in tool_def.parameters if p.required],
            },
        })

    # Initialize ToolCallingInterpreter with hot tool support + asset visibility
    tool_calling_interpreter = ToolCallingInterpreter(
        tool_registry=tool_registry,
        tool_calling_engine=tool_calling_engine,
        memory=light_brain_memory,
        continuation_service=None,
        hot_tool_manager=hot_tool_manager,
        runtime_center=runtime_center,  # For asset visibility in prompt
    )

    light_brain_gateway = LightBrainGateway(
        memory=light_brain_memory,
        interpreter=tool_calling_interpreter,  # Phase E.2: unified tool-aware interpreter
        app_catalog=app_catalog,
        app_registry_service=app_registry,
        app_lifecycle_service=lifecycle,
        app_runtime_host=runtime_host,
        runtime_center=runtime_center,
        app_installer=app_installer,
        skill_registry=skill_factory,
        meta_app_orchestrator=meta_app_orchestrator,
        app_design_orchestrator=app_design_orchestrator,
        llm_responder=llm_responder,
        persistence_service=persistence_service,
        interactive_app=interactive_app,
        interactive_app_workflow=interactive_app_workflow,
        permission_skill=permission_skill,
        tool_registry=tool_registry,
        orchestrator_bridge=g1g2_bridge,
        app_refinement_orchestrator=app_refinement_orchestrator,
        system_catalog=system_catalog,
        asset_tool_executor=asset_tool_executor,
        package_manager_executor=package_manager_executor,
        user_service=user_service,
        message_bus=g1g2_bus,  # Pass MessageBus for RPC-based service calls
        config_center=config_center,  # Pass ConfigCenter for default app-skill binding
        master_control=master_control,  # Pass MasterControl for centralized execution
    )

    runtime_center.register_asset(
        AssetDescriptor(
            asset_id="asset:light_brain_gateway:v1",
            asset_type=AssetType.SERVICE,
            asset_kind=AssetKind.CORE_RUNTIME,
            version="1.0.0",
            owner_type="system",
            owner_id="system",
            source_of_truth="runtime",
            status=AssetState.ACTIVE,
            capabilities=[
                AssetCapability(name="list assets", description="List runtime assets through gateway", method="list_assets", side_effect_level="read"),
                AssetCapability(name="query asset info", description="Query runtime asset info through gateway", method="query_asset_info", side_effect_level="read"),
                AssetCapability(name="call asset method", description="Invoke runtime asset method through gateway", method="call_asset_method", side_effect_level="write"),
            ],
            invoke_contract={"kind": "service", "service_name": "light_brain_gateway"},
            health_contract={"heartbeat": False},
            name="light_brain_gateway",
            description="Unified user interaction gateway",
            tags=["phase-h", "core-runtime"],
            metadata={"python_type": type(light_brain_gateway).__name__},
        ),
        service_ref=light_brain_gateway,
        method_mappings={
            "list_assets": lambda filter="": asset_tool_executor.execute("list_assets", {"filter": filter}, "system").data,
            "query_asset_info": lambda asset_id: asset_tool_executor.execute("query_asset_info", {"asset_id": asset_id}, "system").data,
            "call_asset_method": lambda asset_id, method, params=None: asset_tool_executor.execute("call_asset_method", {"asset_id": asset_id, "method": method, "params": params or {}}, "system").data,
        },
    )

    # -- Phase I: Register system services as MessageBus Workers ----------------
    from app.services.system_lifecycle_worker import SystemLifecycleWorker
    from app.services.system_app_registry_worker import SystemAppRegistryWorker
    from app.services.system_meta_app_worker import SystemMetaAppWorker
    from app.services.system_app_refinement_worker import SystemAppRefinementWorker
    from app.services.system_config_center_worker import SystemConfigCenterWorker

    lifecycle_worker = SystemLifecycleWorker(g1g2_bus, lifecycle)
    app_registry_worker = SystemAppRegistryWorker(g1g2_bus, app_registry)
    meta_app_worker = SystemMetaAppWorker(g1g2_bus, meta_app_orchestrator)
    refinement_worker = SystemAppRefinementWorker(g1g2_bus, app_refinement_orchestrator)
    config_center_worker = SystemConfigCenterWorker(g1g2_bus, config_center)

    # Register workers on MessageBus
    import asyncio
    g1g2_bus.register_worker("system.lifecycle", asyncio.Queue())
    g1g2_bus.register_worker("system.app_registry", asyncio.Queue())
    g1g2_bus.register_worker("system.meta_app", asyncio.Queue())
    g1g2_bus.register_worker("system.app_refinement", asyncio.Queue())
    g1g2_bus.register_worker("system.config_center", asyncio.Queue())
    logger.info("Phase I: 5 system service Workers registered on MessageBus")

    # Wire tool registry and system catalog into interpreter for tool-aware LLM parsing
    light_brain_interpreter.set_tool_registry(tool_registry)
    light_brain_interpreter.set_llm_responder(llm_responder)
    if system_catalog is not None:
        light_brain_interpreter.set_system_catalog(system_catalog)
    if runtime_center is not None:
        light_brain_interpreter.set_runtime_context_provider(runtime_center)
    # Wire LLM to workflow after gateway is created
    interactive_app_workflow._llm = llm_responder

    # -- G.1/G.2: Register skill metadata for orchestrator-facing intents -------
    # Runtime no longer wraps LightBrainGateway handlers into MessageBus workers.
    # The gateway remains a caller; skill execution lives in dedicated workers / services.
    g1g2_system_skill_meta: dict[str, Any] = {
        "greet": {"name": "greet", "description": "打招呼/问候"},
        "list_apps": {"name": "list_apps", "description": "查看 App 列表"},
        "query_status": {"name": "query_status", "description": "查询系统状态"},
        "query_help": {"name": "query_help", "description": "查看帮助"},
        "create_app": {"name": "create_app", "description": "创建 App"},
        "start_app": {"name": "start_app", "description": "启动 App"},
        "stop_app": {"name": "stop_app", "description": "停止 App"},
        "pause_app": {"name": "pause_app", "description": "暂停 App"},
        "resume_app": {"name": "resume_app", "description": "恢复 App"},
        "query_app": {"name": "query_app", "description": "查询 App 详情"},
        "modify_app": {"name": "modify_app", "description": "修改 App"},
        "delete_app": {"name": "delete_app", "description": "删除 App"},
        "grant_admin": {"name": "grant_admin", "description": "授予管理员权限"},
        "grant_root": {"name": "grant_root", "description": "授予 root 权限"},
        "revoke_role": {"name": "revoke_role", "description": "撤销角色"},
        "show_permissions": {"name": "show_permissions", "description": "查看权限"},
        "list_users": {"name": "list_users", "description": "列出用户"},
        "show_self": {"name": "show_self", "description": "查看自身信息"},
    }
    g1g2_bridge.register_system_skills(
        meta_entries=g1g2_system_skill_meta,
    )
    logger.info(
        "G.1/G.2: metadata registered for %d orchestrator-facing intents",
        len(g1g2_system_skill_meta),
    )

    # -- Auth & Session & Pipeline services -------------------------------------
    auth_service = AuthService(user_service=user_service)
    session_router = SessionRouter(user_service=user_service)
    pipeline_service = PipelineService()

    # -- Restore persisted state (if available) ---------------------------------
    try:
        restore_result = persistence_service.restore_state(
            lifecycle=lifecycle,
            runtime_host=runtime_host,
            registry=app_registry,
            catalog=app_catalog,
            light_brain_memory=light_brain_memory,
        )
        if restore_result.get("status") == "restored":
            pass  # State restored successfully
    except Exception as e:
        # Best-effort: don't crash on restore failure
        logging.getLogger(__name__).warning("State restore failed, starting fresh: %s", e)

    return locals()
