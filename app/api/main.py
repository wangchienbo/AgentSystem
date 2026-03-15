from fastapi import FastAPI

from app.services.requirement_router import RequirementRouter

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

@app.post("/route-requirement")
def route_requirement(payload: dict[str, str]) -> dict:
    text = payload.get("text", "")
    return router.route(text).model_dump()
