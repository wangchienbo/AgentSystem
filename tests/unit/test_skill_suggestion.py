from fastapi.testclient import TestClient

from app.api.main import app
from app.models.experience import ExperienceRecord
from app.models.skill_suggestion import SkillSuggestionRequest
from app.services.experience_store import ExperienceStore
from app.services.skill_risk_policy import SkillRiskPolicyService
from app.services.skill_suggestion import SkillSuggestionService


client = TestClient(app)


class StubModelSuggester:
    def __init__(self, available: bool = True, should_fail: bool = False) -> None:
        self._available = available
        self._should_fail = should_fail

    def is_available(self) -> bool:
        return self._available

    def suggest(self, experience: ExperienceRecord, fallback_skill_id: str):
        if self._should_fail:
            raise ValueError("model failed")
        from app.models.skill_blueprint import SkillBlueprint

        return SkillBlueprint(
            skill_id=fallback_skill_id,
            name="Model Suggested Skill",
            goal=f"Use model synthesis for {experience.experience_id}",
            inputs=["context", "experience_summary"],
            outputs=["skill_blueprint"],
            steps=[
                "analyze the runtime experience",
                "extract repeated strategy",
                "return reusable skill blueprint",
            ],
            related_experience_ids=[experience.experience_id],
        )


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



def test_skill_suggestion_uses_model_when_available() -> None:
    store = ExperienceStore()
    service = SkillSuggestionService(experience_store=store, model_suggester=StubModelSuggester())
    store.add_experience(
        ExperienceRecord(
            experience_id="exp.runtime.003",
            title="Runtime review for planner",
            summary="经常需要先提炼目标再生成动作计划。",
            source="runtime",
        )
    )

    result = service.suggest(SkillSuggestionRequest(experience_id="exp.runtime.003"))

    assert result.suggestion.name == "Model Suggested Skill"
    assert result.suggestion.outputs == ["skill_blueprint"]



def test_skill_suggestion_falls_back_when_model_fails() -> None:
    store = ExperienceStore()
    service = SkillSuggestionService(experience_store=store, model_suggester=StubModelSuggester(should_fail=True))
    store.add_experience(
        ExperienceRecord(
            experience_id="exp.runtime.004",
            title="Runtime review for fallback",
            summary="模型输出不稳定时仍需保留规则链路。",
            source="runtime",
        )
    )

    result = service.suggest(SkillSuggestionRequest(experience_id="exp.runtime.004"))

    assert result.suggestion.name.startswith("Suggested Skill for")
    assert any("apply rule distilled from experience" in step for step in result.suggestion.steps)



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



def test_skill_suggestion_includes_risk_governance_context_when_policy_pressure_exists() -> None:
    store = ExperienceStore()
    risk_policy = SkillRiskPolicyService()
    risk_policy.record_event(skill_id="skill.blocked.demo", event_type="policy_blocked", reason="blocked for safety")
    service = SkillSuggestionService(experience_store=store, risk_policy=risk_policy)
    store.add_experience(
        ExperienceRecord(
            experience_id="exp.runtime.005",
            title="Runtime review under governance pressure",
            summary="最近生成型能力多次被风险策略拦截。",
            source="runtime",
        )
    )

    result = service.suggest(SkillSuggestionRequest(experience_id="exp.runtime.005"))

    assert result.governance_context["risk_governance_enabled"] is True
    assert result.governance_context["blocked_events"] >= 1
    assert result.governance_context["recent_policy_pressure"] is True
    assert any("avoid shell/network side effects" in step for step in result.suggestion.steps)



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
