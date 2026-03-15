from fastapi import FastAPI

from app.core.errors import map_domain_error

from app.services.requirement_router import RequirementRouter
from app.services.skill_control import SkillControlService
from app.services.experience_store import ExperienceStore
from app.models.skill_control import SkillRegistryEntry, SkillVersion
from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint
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
