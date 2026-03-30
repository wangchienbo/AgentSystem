from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_requirement_clarify_api_returns_structured_spec() -> None:
    response = client.post("/requirements/clarify", json={"text": "写一个表单字段校验 skill，把输入统一转换成结构化 JSON，并检查缺失字段"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["requirement_type"] == "skill"
    assert payload["readiness"] == "ready"
    assert "user_input" in payload["inputs"]



def test_requirement_readiness_api_returns_actionable_summary() -> None:
    response = client.post("/requirements/readiness", json={"text": "这个流程有很多页面点击和表单操作，我先演示一遍，你再生成应用"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"] == "needs_demo"
    assert payload["needs_demo"] is True
    assert len(payload["recommended_questions"]) >= 1
