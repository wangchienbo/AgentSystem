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
    persistence_health = PersistenceHealthService(store=runtime_store)
    upgrade_log_service = UpgradeLogService()
    blueprint_compare = BlueprintCompareService()
    upgrade_service = UpgradeService(
        lifecycle=lifecycle,
        log_service=upgrade_log_service,
        compare_service=blueprint_compare,
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
    meta_app_bootstrap = MetaAppBootstrapService(model_router=model_router)
    meta_app_orchestrator = MetaAppCreationOrchestrator(
        meta_app_bootstrap=meta_app_bootstrap,
        skill_factory=skill_factory,
        lifecycle=lifecycle,
        runtime_host=runtime_host,
        app_registry=app_registry,
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
    from app.services.tool_registry import ToolRegistry, ToolDefinition, ToolParameter
    from app.services.system_catalog import SystemCatalog, CatalogEntry
    from app.services.asset_tools import AssetToolExecutor, make_all_asset_tools

    # Asset catalog — persistent registry with self-registration
    system_catalog = SystemCatalog()
    logger.info("System catalog loaded: %d entries", system_catalog.count())

    # Asset tool executor — bridges LLM tool calls to registry
    asset_tool_executor = AssetToolExecutor(registry=system_catalog)

    # Tool registry
    tool_registry = ToolRegistry()

    # Register asset tools into the tool registry
    for tool_def in make_all_asset_tools():
        tool_registry.register(ToolDefinition(
            name=tool_def.name,
            description=tool_def.description,
            parameters=[ToolParameter(name=p.name, type=p.type, description=p.description, required=p.required) for p in tool_def.parameters],
            category="asset",
        ))

    # Asset self-registration hooks — injected into lifecycle
    def _on_asset_start(app_instance_id: str) -> None:
        """Register an asset when it starts running."""
        try:
            instance = lifecycle.get_instance(app_instance_id)
            entry = CatalogEntry(
                asset_id=f"app.{instance.id}",
                asset_type="app",
                owner_id=f"user.{instance.owner_user_id}" if instance.owner_user_id != "system" else "system",
                name=instance.id,
                description=f"App instance: {instance.id}",
                status="running",
                visibility="public" if instance.owner_user_id == "system" else "private",
            )
            system_catalog.register(entry)
            logger.info("Asset self-registered: %s", entry.asset_id)
        except Exception as e:
            logger.warning("Asset start hook failed for %s: %s", app_instance_id, e)

    def _on_asset_stop(app_instance_id: str) -> None:
        """Unregister an asset when it stops."""
        try:
            system_catalog.unregister(f"app.{app_instance_id}")
            logger.info("Asset unregistered: app.%s", app_instance_id)
        except Exception as e:
            logger.warning("Asset stop hook failed for %s: %s", app_instance_id, e)

    lifecycle.set_asset_hooks(on_asset_start=_on_asset_start, on_asset_stop=_on_asset_stop)

    light_brain_memory = LightBrainMemory()
    light_brain_interpreter = LightBrainInterpreter()
    llm_responder = LLMResponder(model_router=model_router)
    light_brain_gateway = LightBrainGateway(
        memory=light_brain_memory,
        interpreter=light_brain_interpreter,
        app_catalog=app_catalog,
        app_registry_service=app_registry,
        app_lifecycle_service=lifecycle,
        app_runtime_host=runtime_host,
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
        user_service=user_service,
    )

    # Wire tool registry and system catalog into interpreter for tool-aware LLM parsing
    light_brain_interpreter.set_tool_registry(tool_registry)
    # Wire LLM to workflow after gateway is created
    interactive_app_workflow._llm = llm_responder

    # -- G.1/G.2: Register Gateway handlers as Workers on the MessageBus -------
    # Wrap Gateway async handlers and register them as Bus Workers so the
    # Orchestrator can route to them through the new chain.
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
    registered_count = g1g2_bridge.register_gateway_handlers(
        gateway=light_brain_gateway,
    )
    # Also register meta entries for skills that may not have a direct handler
    g1g2_bridge.register_system_skills(
        handlers={},
        meta_entries=g1g2_system_skill_meta,
    )
    logger.info(
        "G.1/G.2: %d gateway handlers registered as Workers, %d meta skills registered",
        registered_count, len(g1g2_system_skill_meta),
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
