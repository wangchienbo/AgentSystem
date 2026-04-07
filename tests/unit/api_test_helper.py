from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.runtime import build_runtime
from app.bootstrap.skills import bootstrap_builtin_skills
from app.bootstrap.catalog import bootstrap_demo_catalog


def create_isolated_test_client(tmp_path: Path) -> TestClient:
    app = FastAPI(title="AgentSystem App OS", version="0.1.0-test")
    services = build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )

    bootstrap_builtin_skills(services["skill_runtime"], services)
    bootstrap_demo_catalog(services["app_registry"], services["app_catalog"])

    def _register(method: str, path: str):
        def decorator(func):
            getattr(app, method)(path)(func)
            return func
        return decorator

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

    @_register("post", "/events/publish")
    def publish_event(payload: dict) -> dict:
        return services["event_bus"].publish(
            payload["event_name"],
            source=payload["source"],
            app_instance_id=payload.get("app_instance_id"),
            payload=payload.get("payload", {}),
        ).model_dump(mode="json")

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

    @_register("post", "/registry/apps/{blueprint_id}/install")
    def install_app(blueprint_id: str, payload: dict) -> dict:
        return services["app_installer"].install_app(blueprint_id, user_id=payload["user_id"]).model_dump(mode="json")

    @_register("post", "/app-contexts/{app_instance_id}/entries")
    def append_context_entry(app_instance_id: str, payload: dict) -> dict:
        return services["app_context_store"].append_entry(
            app_instance_id=app_instance_id,
            section=payload["section"],
            key=payload["key"],
            value=payload["value"],
            tags=payload.get("tags", []),
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
        from app.models.proposal_review import ProposalReviewRequest
        return services["proposal_review"].review(ProposalReviewRequest(**payload)).model_dump(mode="json")

    return TestClient(app)
