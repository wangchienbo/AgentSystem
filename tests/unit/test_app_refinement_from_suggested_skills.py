from fastapi.testclient import TestClient

from app.api.main import app
from app.models.experience import ExperienceRecord
from app.models.skill_suggestion import SkillSuggestionRequest
from app.services.experience_store import ExperienceStore
from app.services.skill_suggestion import SkillSuggestionService


client = TestClient(app)


def test_app_refinement_from_suggested_skills_api_flow() -> None:
    review_install = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "app-refine-user"},
    )
    assert review_install.status_code == 200
    app_instance_id = review_install.json()["app_instance_id"]

    client.post(
        "/events/publish",
        json={
            "event_name": "assistant.responded",
            "source": "api-test",
            "app_instance_id": app_instance_id,
            "payload": {"kind": "reply"},
        },
    )
    namespaces_response = client.get("/data/namespaces", params={"app_instance_id": app_instance_id})
    app_data_namespace = next(item for item in namespaces_response.json() if item["namespace_type"] == "app_data")
    client.post(
        f"/data/namespaces/{app_data_namespace['namespace_id']}/records",
        json={"key": "reply-log", "value": {"status": "ok"}, "tags": ["reply"]},
    )
    review_response = client.post(
        "/practice/review",
        json={"app_instance_id": app_instance_id},
    )
    experience_id = review_response.json()["experience"]["experience_id"]

    suggestion_response = client.post(
        "/skills/suggest-from-experience",
        json={"experience_id": experience_id, "persist": True},
    )
    assert suggestion_response.status_code == 200
    suggestion_skill_id = suggestion_response.json()["suggestion"]["skill_id"]

    refine_response = client.post(
        "/apps/refine-from-suggested-skills",
        json={
            "blueprint_id": "bp.refined.from.suggested.skills",
            "name": "Refined From Suggested Skills",
            "goal": "assemble app refinement from suggested skills",
            "experience_id": experience_id,
            "workflow_id": "wf.refined.suggested",
        },
    )
    assert refine_response.status_code == 200, refine_response.text
    payload = refine_response.json()
    assert payload["blueprint"]["id"] == "bp.refined.from.suggested.skills"
    assert suggestion_skill_id in payload["reused_skill_ids"]
    assert payload["app_result"]["workflow_id"] == "wf.refined.suggested"
    assert payload["blueprint"]["required_skills"] == payload["reused_skill_ids"]


def test_skill_suggestion_service_can_feed_refinement_selection() -> None:
    store = ExperienceStore()
    suggestion = SkillSuggestionService(experience_store=store)
    store.add_experience(
        ExperienceRecord(
            experience_id="exp.refine.001",
            title="Refinement candidate",
            summary="将重复回复模式提炼成技能，再组装成应用。",
            source="runtime",
        )
    )
    result = suggestion.suggest(SkillSuggestionRequest(experience_id="exp.refine.001", persist=True))
    related = store.suggest_skills_for_experience("exp.refine.001")
    assert result.suggestion.skill_id in [item.skill_id for item in related]
