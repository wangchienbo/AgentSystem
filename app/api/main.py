from fastapi import FastAPI

from app.core.errors import map_domain_error

from app.services.requirement_router import RequirementRouter
from app.services.skill_control import SkillControlService
from app.services.experience_store import ExperienceStore
from app.services.demonstration_extractor import DemonstrationExtractor
from app.services.lifecycle import AppLifecycleService, LifecycleError
from app.services.runtime_host import AppRuntimeHostService, RuntimeHostError
from app.services.runtime_state_store import RuntimeStateStore
from app.services.scheduler import SchedulerService, SchedulerError
from app.services.supervisor import SupervisorService, SupervisorError
from app.services.app_catalog import AppCatalogService, AppCatalogError
from app.services.app_context_store import AppContextStore, AppContextStoreError
from app.services.app_data_store import AppDataStore, AppDataStoreError
from app.services.app_registry import AppRegistryService, AppRegistryError
from app.services.app_installer import AppInstallerService, AppInstallerError
from app.services.event_bus import EventBusService, EventBusError
from app.services.interaction_gateway import InteractionGateway
from app.services.practice_review import PracticeReviewService, PracticeReviewError
from app.services.priority_analysis import PriorityAnalysisService, PriorityAnalysisError
from app.services.proposal_review import ProposalReviewService, ProposalReviewError
from app.services.self_refinement import SelfRefinementService, SelfRefinementError
from app.services.skill_suggestion import SkillSuggestionService, SkillSuggestionError
from app.services.model_skill_suggester import ModelSkillSuggester
from app.services.model_self_refiner import ModelSelfRefiner
from app.services.workflow_executor import WorkflowExecutorService, WorkflowExecutorError
from app.services.workflow_subscription import WorkflowSubscriptionService, WorkflowSubscriptionError
from app.services.skill_runtime import SkillRuntimeService, SkillRuntimeError
from app.models.event_bus import EventSubscription
from app.models.workflow_subscription import WorkflowEventSubscription
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult
from app.models.patch_proposal import SelfRefinementRequest
from app.models.practice_review import PracticeReviewRequest
from app.models.priority_analysis import PriorityAnalysisRequest
from app.models.proposal_review import ProposalReviewRequest
from app.models.skill_suggestion import SkillSuggestionRequest
from app.models.skill_control import SkillRegistryEntry, SkillVersion
from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint
from app.models.demonstration import DemonstrationRecord
from app.models.app_instance import AppInstance
from app.models.interaction import AppCatalogEntry, UserCommand
from app.models.registry import AppRegistryEntry
from app.models.scheduling import ScheduleRecord, SupervisionPolicy
from app.services.skill_control import SkillControlError

from app.models.app_blueprint import AppBlueprint

app = FastAPI(title="AgentSystem App OS", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": "0.1.0"}


@app.post("/blueprints/validate")
def validate_blueprint(blueprint: AppBlueprint) -> dict[str, object]:
    missing = []
    if not blueprint.roles:
        missing.append("roles")
    if not blueprint.workflows:
        missing.append("workflows")
    if not blueprint.required_modules:
        missing.append("required_modules")
    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "blueprint_id": blueprint.id,
    }


router = RequirementRouter()
skill_control = SkillControlService()
experience_store = ExperienceStore()
demonstration_extractor = DemonstrationExtractor()
runtime_store = RuntimeStateStore()
app_data_store = AppDataStore(store=runtime_store)
app_data_store.ensure_skill_asset_namespace()
lifecycle = AppLifecycleService(store=runtime_store)
runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=runtime_store)
app_context_store = AppContextStore(lifecycle=lifecycle, store=runtime_store, runtime_host=runtime_host)
scheduler = SchedulerService(lifecycle=lifecycle, runtime_host=runtime_host, store=runtime_store)
event_bus = EventBusService(scheduler=scheduler, store=runtime_store)
supervisor = SupervisorService(runtime_host=runtime_host, store=runtime_store)
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
)
app_catalog = AppCatalogService()
skill_runtime = SkillRuntimeService(store=runtime_store)


def _demo_echo_skill(request: SkillExecutionRequest) -> SkillExecutionResult:
    payload = request.config.get("payload", request.inputs)
    return SkillExecutionResult(
        skill_id=request.skill_id,
        status="completed",
        output={"echo": payload, "step_id": request.step_id},
    )


skill_runtime.register_handler("skill.echo", _demo_echo_skill)
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
interaction_gateway = InteractionGateway(
    catalog=app_catalog,
    router=router,
    lifecycle=lifecycle,
    runtime_host=runtime_host,
    installer=app_installer,
    context_store=app_context_store,
)
skill_control.register(
    SkillRegistryEntry(
        skill_id="core.skill.control",
        name="Human Skill Control Interface",
        immutable_interface=True,
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="protected control surface")],
        dependencies=[],
    )
)
app_registry.register_blueprint(
    AppBlueprint(
        id="bp.workspace.assistant",
        name="Workspace Assistant",
        goal="长期运行的工作台助手 app",
        roles=[],
        tasks=[],
        workflows=[{"id": "wf.assistant", "name": "assistant loop", "triggers": ["manual"], "steps": []}],
        required_modules=["state.get"],
        required_skills=["requirement.clarify"],
        runtime_policy={
            "execution_mode": "service",
            "activation": "on_demand",
            "restart_policy": "on_failure",
            "persistence_level": "full",
            "idle_strategy": "keep_alive",
        },
    )
)
app_registry.register_blueprint(
    AppBlueprint(
        id="bp.pipeline.executor",
        name="Pipeline Executor",
        goal="一次性流水线执行 app",
        roles=[],
        tasks=[],
        workflows=[{"id": "wf.pipeline", "name": "pipeline run", "triggers": ["manual"], "steps": []}],
        required_modules=["state.set"],
        required_skills=["workflow.suggest"],
        runtime_policy={
            "execution_mode": "pipeline",
            "activation": "on_demand",
            "restart_policy": "never",
            "persistence_level": "standard",
            "idle_strategy": "stop",
        },
    )
)
app_catalog.register(
    AppCatalogEntry(
        app_id="app.workspace.assistant",
        name="Workspace Assistant",
        description="长期运行的工作台助手 app",
        execution_mode="service",
        trigger_phrases=["打开助手", "assistant", "workspace assistant", "打开工作台"],
        blueprint_id="bp.workspace.assistant",
    )
)
app_catalog.register(
    AppCatalogEntry(
        app_id="app.pipeline.executor",
        name="Pipeline Executor",
        description="一次性流水线执行 app",
        execution_mode="pipeline",
        trigger_phrases=["执行流水线", "pipeline", "run pipeline", "跑一下流程"],
        blueprint_id="bp.pipeline.executor",
    )
)

@app.post("/route-requirement")
def route_requirement(payload: dict[str, str]) -> dict:
    text = payload.get("text", "")
    return router.route(text).model_dump()

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
        return skill_control.rollback_skill(skill_id, payload["target_version"]).model_dump(mode="json")
    except SkillControlError as error:
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
def list_workflow_failures(app_instance_id: str | None = None) -> list[dict]:
    return [item.model_dump(mode="json") for item in workflow_executor.list_recent_failures(app_instance_id)]


@app.post("/apps/{app_instance_id}/workflows/retry-last-failure")
def retry_last_failed_workflow(app_instance_id: str) -> dict:
    try:
        return workflow_executor.retry_last_failure(app_instance_id).model_dump(mode="json")
    except (WorkflowExecutorError,) as error:
        raise map_domain_error(error) from error


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
