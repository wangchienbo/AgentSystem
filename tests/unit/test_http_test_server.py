from __future__ import annotations

from fastapi.testclient import TestClient

from app.system.http_test_server import app, user_sessions, conversation_history


client = TestClient(app)


def test_api_chat_accepts_new_explicit_session_id_after_login() -> None:
    user_sessions.clear()
    conversation_history.clear()
    user_sessions["session_tester"] = {
        "username": "tester",
        "session_id": "session_tester",
        "login_time": "2026-04-26T00:00:00",
        "last_active": "2026-04-26T00:00:00",
    }
    client.cookies.set("session_id", "session_tester")

    response = client.post(
        "/api/chat",
        json={
            "message": "hello",
            "session_id": "session_custom_regression",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session_custom_regression"
    assert "session_custom_regression" in user_sessions
    assert "session_custom_regression" in conversation_history


def test_api_chat_exposes_structured_answer_payload() -> None:
    user_sessions.clear()
    conversation_history.clear()
    user_sessions["session_tester"] = {
        "username": "tester",
        "session_id": "session_tester",
        "login_time": "2026-04-26T00:00:00",
        "last_active": "2026-04-26T00:00:00",
    }
    conversation_history["session_tester"] = []
    client.cookies.set("session_id", "session_tester")

    from unittest.mock import AsyncMock, patch
    from app.models.chat import ChatMessageResponse
    from app.models.cognition import SelfModel, StructuredAnswer, StructuredClaim

    structured = StructuredAnswer(
        self_model=SelfModel(capability_state="tool_required", tool_dependence_state="required", confidence_state=0.9),
        claim=StructuredClaim(text="已确认默认值是 json", evidence_grade="excerpt", confidence=0.9),
        evidence=[{"grade": "excerpt", "source_type": "read_file", "source_ref": "app/system/catalog/resource_center.py"}],
        unverified_points=["尚未验证其他覆盖路径"],
        text="已确认默认值是 json",
    )

    fake_reply = ChatMessageResponse(type="text", content="已确认默认值是 json", session_id="session_tester", structured_answer=structured)

    with patch("app.system.http_test_server.gateway.receive_message", new=AsyncMock(return_value=fake_reply)) as mocked_receive:
        response = client.post("/api/chat", json={"message": "请查默认值"})

    assert mocked_receive.await_count == 1
    assert response.status_code == 200
    data = response.json()
    assert data["structured_answer"] is not None
    assert data["structured_answer"]["claim"]["text"] == "已确认默认值是 json"
    assert data["structured_answer"]["self_model"]["human_equivalence_state"] == "non_human_equivalent"
