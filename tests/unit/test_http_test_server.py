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
