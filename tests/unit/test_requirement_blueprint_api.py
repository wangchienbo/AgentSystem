from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_requirement_blueprint_draft_api_returns_blueprint_for_ready_app_request() -> None:
    response = client.post(
        "/requirements/blueprint-draft",
        json={"text": "帮我做一个客服审批系统 app，要能提交工单、分配处理人，并记录失败重试日志和权限边界"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"].startswith("bp.requirement.")
    assert len(payload["roles"]) >= 1
    assert payload["runtime_policy"]["execution_mode"] == "service"



def test_requirement_blueprint_draft_api_fails_for_non_ready_requirement() -> None:
    response = client.post(
        "/requirements/blueprint-draft",
        json={"text": "这个流程有很多页面点击和表单操作，我先演示一遍，你再生成应用"},
    )

    assert response.status_code == 400
    assert "not ready" in response.json()["detail"]
