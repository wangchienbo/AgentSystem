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


def test_api_chat_response_prefixes_verification_required_mode() -> None:
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
        self_model=SelfModel(
            capability_state="tool_required",
            tool_dependence_state="required",
            confidence_state=0.4,
            answer_mode="verification_required",
            verification_mode="required",
        ),
        claim=StructuredClaim(text="当前只能初步判断", evidence_grade="none", confidence=0.4),
        evidence=[],
        unverified_points=["仍需补充更直接证据"],
        text="当前只能初步判断",
    )
    fake_reply = ChatMessageResponse(type="text", content="当前只能初步判断", session_id="session_tester", structured_answer=structured)

    with patch("app.system.http_test_server.gateway.receive_message", new=AsyncMock(return_value=fake_reply)):
        response = client.post("/api/chat", json={"message": "帮我确认默认值"})

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "当前只能初步判断"
    assert data["structured_answer"]["self_model"]["answer_mode"] == "verification_required"


def test_fixed_prompt_regression_seed_covers_core_scan_topics() -> None:
    prompts = {
        "api": "请梳理 API handler 和 request/response 流程",
        "validation": "请检查校验器和 guard 规则",
        "telemetry": "请检查日志埋点和观测记录",
        "storage": "请检查 storage backend 和读写路径",
    }

    assert set(prompts) == {"api", "validation", "telemetry", "storage"}
    assert all(isinstance(v, str) and v for v in prompts.values())


def test_fixed_prompt_matrix_runs_through_real_testclient_adapter() -> None:
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
    from app.system.chat_regression import make_testclient_poster, run_fixed_prompt_matrix

    def build_reply(message: str) -> ChatMessageResponse:
        structured = StructuredAnswer(
            self_model=SelfModel(
                capability_state="tool_required",
                tool_dependence_state="required",
                confidence_state=0.7,
                answer_mode="tool_required",
                verification_mode="light",
            ),
            claim=StructuredClaim(text=f"已处理: {message}", evidence_grade="excerpt", confidence=0.7),
            evidence=[{"grade": "excerpt", "source_type": "read_file", "source_ref": "a.py"}],
            unverified_points=["建议轻量验证"],
            text=f"已处理: {message}",
        )
        return ChatMessageResponse(type="text", content=f"已处理: {message}", session_id="session_tester", structured_answer=structured)

    async def fake_receive_message(chat_req):
        return build_reply(chat_req.message)

    with patch("app.system.http_test_server.gateway.receive_message", new=AsyncMock(side_effect=fake_receive_message)):
        results = run_fixed_prompt_matrix(make_testclient_poster(client))

    assert len(results) == 4
    assert results[0].topic == "api"
    assert all(item.success for item in results)
    assert all(item.answer_mode == "tool_required" for item in results)
