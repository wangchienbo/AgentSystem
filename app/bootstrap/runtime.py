from __future__ import annotations

from app.services.app_catalog import AppCatalogService
from app.services.system_skills.app_config import AppConfigService
from app.services.app_context_store import AppContextStore
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.app_registry import AppRegistryService
from app.services.context_compaction import ContextCompactionService
from app.services.system_skills.context import ContextSkillService
from app.services.blueprint_validation import BlueprintValidationService
from app.services.skill_validation import SkillValidationService
from app.services.demonstration_extractor import DemonstrationExtractor
from app.services.event_bus import EventBusService
from app.services.experience_store import ExperienceStore
from app.services.interaction_gateway import InteractionGateway
from app.services.lifecycle import AppLifecycleService
from app.services.model_self_refiner import ModelSelfRefiner
from app.services.model_skill_suggester import ModelSkillSuggester
from app.services.practice_review import PracticeReviewService
from app.services.priority_analysis import PriorityAnalysisService
from app.services.proposal_review import ProposalReviewService
from app.services.requirement_router import RequirementRouter
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService
from app.services.schema_registry import SchemaRegistryService
from app.services.self_refinement import SelfRefinementService
from app.services.skill_control import SkillControlService
from app.services.skill_runtime import SkillRuntimeService
from app.services.skill_suggestion import SkillSuggestionService
from app.services.supervisor import SupervisorService
from app.services.system_skills.state_audit import SystemAuditService, SystemStateService
from app.services.workflow_executor import WorkflowExecutorService
from app.services.workflow_subscription import WorkflowSubscriptionService


def build_runtime() -> dict[str, object]:
    router = RequirementRouter()
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
    practice_review = PracticeReviewService(
        event_bus=event_bus,
        data_store=app_data_store,
        experience_store=experience_store,
        context_store=app_context_store,
    )
    model_skill_suggester = ModelSkillSuggester()
    skill_suggestion = SkillSuggestionService(experience_store=experience_store, model_suggester=model_skill_suggester)
    app_registry = AppRegistryService(store=runtime_store)
    model_self_refiner = ModelSelfRefiner()
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
    skill_runtime = SkillRuntimeService(store=runtime_store, schema_registry=schema_registry)
    workflow_executor = WorkflowExecutorService(
        registry=app_registry,
        lifecycle=lifecycle,
        data_store=app_data_store,
        event_bus=event_bus,
        context_store=app_context_store,
        skill_runtime=skill_runtime,
        store=runtime_store,
    )
    workflow_subscription = WorkflowSubscriptionService(
        workflow_executor=workflow_executor,
        store=runtime_store,
    )
    context_compaction = ContextCompactionService(
        app_context_store=app_context_store,
        workflow_executor=workflow_executor,
        store=runtime_store,
    )
    workflow_executor._context_compaction = context_compaction
    interaction_gateway = InteractionGateway(
        catalog=app_catalog,
        router=router,
        lifecycle=lifecycle,
        runtime_host=runtime_host,
        installer=app_installer,
        context_store=app_context_store,
    )

    return locals()
