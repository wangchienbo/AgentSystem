from fastapi import FastAPI

from app.core.errors import map_domain_error

from app.services.requirement_router import RequirementRouter
from app.services.skill_control import SkillControlService
from app.services.experience_store import ExperienceStore
from app.services.demonstration_extractor import DemonstrationExtractor
from app.services.lifecycle import AppLifecycleService, LifecycleError
from app.services.runtime_host import AppRuntimeHostService, RuntimeHostError
from app.models.skill_control import SkillRegistryEntry, SkillVersion
from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint
from app.models.demonstration import DemonstrationRecord
from app.models.app_instance import AppInstance
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
lifecycle = AppLifecycleService()
runtime_host = AppRuntimeHostService(lifecycle=lifecycle)
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
