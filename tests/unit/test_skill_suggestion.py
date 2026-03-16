from fastapi.testclient import TestClient

from app.api.main import app
from app.models.experience import ExperienceRecord
from app.models.skill_suggestion import SkillSuggestionRequest
from app.services.experience_store import ExperienceStore
from app.services.skill_suggestion import SkillSuggestionService


client = TestClient(app)


def test_skill_suggestion_generates_blueprint() -> None:
    store = ExperienceStore()
    service = SkillSuggestionService(experience_store=store)
    store.add_experience(
        ExperienceRecord(
            experience_id="exp.runtime.001",
            title="Runtime review for assistant",
            summary="最近多次出现 assistant.responded 事件，并伴随 reply-log 数据沉淀。",
            source="runtime",
            tags=["assistant.responded", "reply"],
            related_apps=["app.workspace.assistant:demo"],
        )
    )

    result = service.suggest(SkillSuggestionRequest(experience_id="exp.runtime.001"))

    assert result.persisted is False
    assert result.suggestion.related_experience_ids == ["exp.runtime.001"]
    assert len(result.suggestion.steps) >= 3


def test_skill_suggestion_can_persist_blueprint() -> None:
    store = ExperienceStore()
    service = SkillSuggestionService(experience_store=store)
    store.add_experience(
        ExperienceRecord(
            experience_id="exp.runtime.002",
            title="Runtime review for pipeline",
            summary="流水线执行后会沉淀 summary 数据记录。",
            source="runtime",
        )
    )

    result = service.suggest(SkillSuggestionRequest(experience_id="exp.runtime.002", persist=True))

    assert result.persisted is True
    assert len(store.list_skill_blueprints()) == 1


def test_skill_suggestion_api_flow() -> None:
    review_install = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "skill-suggest-user"},
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
    assert suggestion_response.json()["persisted"] is True
    assert suggestion_response.json()["suggestion"]["related_experience_ids"] == [experience_id]
