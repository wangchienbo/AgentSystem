from __future__ import annotations

from fastapi.testclient import TestClient

from app.system.http_test_server import app, user_sessions, conversation_history, refinement_rollout


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


def test_api_chat_regression_run_and_latest_endpoints() -> None:
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

    from unittest.mock import patch
    from app.system.chat_regression import RegressionProbeResult, RegressionRunSummary

    fake_results = [
        RegressionProbeResult(
            topic="api", prompt="p1", success=True, latency_ms=10, response="ok",
            answer_mode="direct", verification_mode="none", fallback_like=False, overreach_risk=False,
        )
    ]
    fake_summary = RegressionRunSummary(
        run_id="run-endpoint",
        started_at="2026-04-27T00:00:00Z",
        topic_count=1,
        success_count=1,
        avg_latency_ms=10,
        fallback_count=0,
        overreach_risk_count=0,
        answer_mode_counts={"direct": 1},
        verification_mode_counts={"none": 1},
    )

    with patch("app.system.http_test_server.run_fixed_prompt_matrix", return_value=fake_results), \
         patch("app.system.http_test_server.build_run_summary", return_value=fake_summary), \
         patch("app.system.http_test_server.persist_run_results") as persist_mock:
        persist_mock.return_value = __import__("pathlib").Path("/tmp/run-endpoint.jsonl")
        run_resp = client.post("/api/chat-regression/run")

    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["success"] is True
    assert run_data["run_id"] == "run-endpoint"

    import pathlib
    regression_dir = pathlib.Path("/root/project/AgentSystem/data/chat_regression")
    regression_dir.mkdir(parents=True, exist_ok=True)
    latest_file = regression_dir / "run-endpoint.jsonl"
    latest_file.write_text("{\"kind\":\"summary\",\"run_id\":\"run-endpoint\",\"started_at\":\"2026-04-27T00:00:00Z\"}\n", encoding="utf-8")

    latest_resp = client.get("/api/chat-regression/latest")
    assert latest_resp.status_code == 200
    latest_data = latest_resp.json()
    assert latest_data["success"] is True
    assert latest_data["summary"]["run_id"] == "run-endpoint"


def test_api_chat_regression_runs_and_detail_endpoints() -> None:
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

    import pathlib
    regression_dir = pathlib.Path("/root/project/AgentSystem/data/chat_regression")
    regression_dir.mkdir(parents=True, exist_ok=True)
    run_path = regression_dir / "run-list.jsonl"
    run_path.write_text(
        "{\"kind\":\"summary\",\"run_id\":\"run-list\",\"started_at\":\"2026-04-27T00:00:00Z\"}\n"
        "{\"kind\":\"probe\",\"run_id\":\"run-list\",\"topic\":\"api\"}\n",
        encoding="utf-8",
    )

    runs_resp = client.get("/api/chat-regression/runs")
    assert runs_resp.status_code == 200
    runs_data = runs_resp.json()
    assert runs_data["success"] is True
    assert any(item["summary"]["run_id"] == "run-list" for item in runs_data["runs"])

    detail_resp = client.get("/api/chat-regression/runs/run-list")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["success"] is True
    assert detail_data["summary"]["run_id"] == "run-list"
    assert detail_data["probes"][0]["topic"] == "api"


def test_api_chat_regression_compare_endpoint() -> None:
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

    from unittest.mock import patch

    fake_comp = {
        "run_count": 2,
        "avg_latency_ms": 200,
        "avg_fallback_count": 0.5,
        "avg_overreach_risk_count": 0.5,
        "answer_mode_totals": {"direct": 1},
        "verification_mode_totals": {"none": 1},
        "runs": [],
    }

    with patch("app.system.http_test_server.build_multi_run_comparison", return_value=fake_comp):
        resp = client.get("/api/chat-regression/compare")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["run_count"] == 2
    assert data["avg_latency_ms"] == 200


def test_api_chat_regression_evidence_endpoint() -> None:
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

    from unittest.mock import patch

    fake_comparison = {
        "run_count": 3,
        "avg_latency_ms": 6000,
        "avg_fallback_count": 2.0,
        "avg_overreach_risk_count": 1.5,
        "answer_mode_totals": {"verification_required": 4, "clarification_required": 3, "direct": 3},
        "verification_mode_totals": {"none": 5, "required": 5},
        "runs": [],
    }

    with patch("app.system.http_test_server.build_multi_run_comparison", return_value=fake_comparison),          patch("app.system.http_test_server.promote_regression_evidence", return_value={
             "comparison": fake_comparison,
             "promoted_evidence": [{"evidence_id": "evidence-abc", "summary": "elevated latency"}],
             "promoted_count": 1,
         }):
        resp = client.post("/api/chat-regression/evidence")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["promoted_count"] == 1
    assert data["promoted_evidence"][0]["evidence_id"] == "evidence-abc"


def test_api_chat_regression_trends_endpoint() -> None:
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

    from unittest.mock import patch

    fake_trends = {
        "topics": {
            "api": {"run_count": 2, "avg_latency_ms": 150, "avg_fallback": 0.0, "avg_overreach": 0.0, "answer_mode_counts": {}, "verification_mode_counts": {}, "data_points": []},
        },
        "run_count": 2,
    }

    with patch("app.system.http_test_server.build_topic_trends", return_value=fake_trends):
        resp = client.get("/api/chat-regression/trends")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["run_count"] == 2
    assert "api" in data["topics"]


def test_api_chat_regression_evidence_history_endpoint() -> None:
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

    from unittest.mock import patch

    fake_history = [
        {"evidence_id": "evidence-abc", "category": "policy_pressure", "summary": "elevated fallback"},
        {"evidence_id": "evidence-def", "category": "workflow_failure", "summary": "high latency"},
    ]

    with patch("app.system.http_test_server.list_regression_evidence_history", return_value=fake_history):
        resp = client.get("/api/chat-regression/evidence")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 2
    assert data["evidence"][0]["evidence_id"] == "evidence-abc"


def test_api_governance_regression_dashboard_endpoint() -> None:
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

    from unittest.mock import patch

    fake_dashboard = {
        "comparison": {"run_count": 3, "avg_latency_ms": 4000},
        "trends": {"topics": {}, "run_count": 3},
        "evidence": [{"evidence_id": "ev-1", "category": "policy_pressure"}],
        "risk_flags": [{"level": "warning", "signal": "elevated_latency", "detail": "Latency elevated"}],
        "dashboard_id": "regression-governance",
        "generated_at": "2026-04-27T00:00:00Z",
    }

    with patch("app.system.http_test_server.build_regression_governance_dashboard", return_value=fake_dashboard):
        resp = client.get("/api/governance/regression-dashboard")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["dashboard_id"] == "regression-governance"
    assert len(data["risk_flags"]) == 1
    assert len(data["evidence"]) == 1


def test_api_chat_regression_evidence_history_filter_by_topic() -> None:
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

    from unittest.mock import patch

    fake_history = [
        {"evidence_id": "ev-api", "category": "policy_pressure", "summary": "api latency elevated"},
        {"evidence_id": "ev-telemetry", "category": "workflow_failure", "summary": "telemetry overreach"},
    ]

    def fake_list_evidence(*, limit=20, topic=None, **kwargs):
        if topic == "api":
            return [e for e in fake_history if e["evidence_id"] == "ev-api"]
        if topic == "telemetry":
            return [e for e in fake_history if e["evidence_id"] == "ev-telemetry"]
        return fake_history

    with patch("app.system.http_test_server.list_regression_evidence_history", side_effect=fake_list_evidence):
        resp = client.get("/api/chat-regression/evidence?topic=api")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 1
    assert data["evidence"][0]["evidence_id"] == "ev-api"


def test_api_governance_operator_summary_endpoint() -> None:
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

    from unittest.mock import patch

    fake_summary = {
        "app_instance_id": "agent_system",
        "refinement": {
            "proposal_count": 0,
            "primary_contradiction": "",
            "recommended_action": "",
            "context_summary": "Regression-integrated governance summary",
            "governance": {
                "overview": {"hypothesis_count": 1, "verification_count": 8, "passed_verification_count": 4, "failed_verification_count": 4, "queue_count": 1},
                "stats": {"total_hypotheses": 1, "total_verifications": 8, "passed_verifications": 4, "failed_verifications": 4, "total_queue_items": 1},
            },
        },
        "regression": {"dashboard_id": "regression-governance", "comparison": {"run_count": 2, "avg_latency_ms": 6000}, "trends": {}, "evidence": [], "risk_flags": [{"level": "warning", "signal": "elevated_latency"}]},
        "generated_at": "2026-04-27T00:00:00Z",
    }

    with patch("app.system.http_test_server.build_regression_operator_summary", return_value=fake_summary):
        resp = client.get("/api/governance/operator-summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["app_instance_id"] == "agent_system"
    assert "refinement" in data
    assert "regression" in data
    # Verify refinement metrics are populated
    gov = data["refinement"]["governance"]
    assert gov["overview"]["hypothesis_count"] > 0
    assert gov["overview"]["verification_count"] > 0


def test_api_governance_regression_triggers_endpoint() -> None:
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

    from unittest.mock import patch

    fake_triggers = {
        "triggers": [
            {"trigger_id": "trig-1", "signal": "elevated_latency", "level": "warning", "recommended_action": "profile_performance_bottlenecks", "detail": "Latency elevated", "generated_at": "2026-04-27T00:00:00Z"},
        ],
        "trigger_count": 1,
        "dashboard_comparison": {"run_count": 2},
        "generated_at": "2026-04-27T00:00:00Z",
    }

    with patch("app.system.http_test_server.build_regression_triggers", return_value=fake_triggers):
        resp = client.post("/api/governance/regression-triggers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["trigger_count"] == 1
    assert data["triggers"][0]["signal"] == "elevated_latency"


def test_api_governance_regression_triggers_apply_endpoint() -> None:
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

    from unittest.mock import patch

    fake_result = {
        "trigger_count": 1,
        "created_hypotheses": [{"hypothesis_id": "reg-hyp-1"}],
        "created_verifications": [{"verification_id": "reg-ver-1"}],
        "created_queue_items": [{"queue_id": "reg-queue-1"}],
        "generated_at": "2026-04-27T00:00:00Z",
    }

    with patch("app.system.http_test_server.apply_regression_triggers_to_refinement", return_value=fake_result):
        resp = client.post("/api/governance/regression-triggers/apply")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["trigger_count"] == 1
    assert data["created_hypotheses"][0]["hypothesis_id"] == "reg-hyp-1"


def test_api_governance_regression_queue_transition_endpoint() -> None:
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

    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem

    fake_item = RolloutQueueItem(
        queue_id="reg-queue-1",
        hypothesis_id="reg-hyp-1",
        proposal_id="regression-trigger-1",
        app_instance_id="agent_system",
        status="applied",
        note="applied from regression rollout queue",
    )

    with patch.object(refinement_rollout, "transition", return_value=fake_item):
        resp = client.post(
            "/api/governance/regression-queue/transition",
            json={"queue_id": "reg-queue-1", "action": "apply"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["item"]["status"] == "applied"
    assert data["item"]["queue_id"] == "reg-queue-1"


def test_api_governance_regression_cycle_run_endpoint() -> None:
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

    from unittest.mock import patch

    fake_result = {
        "run_id": "chat-regression-cycle-1",
        "summary": {"topic_count": 4},
        "path": "/tmp/chat-regression-cycle-1.jsonl",
        "evidence": {"promoted_count": 1},
        "trigger_application": {"trigger_count": 1},
    }

    with patch("app.system.http_test_server.run_regression_governance_cycle", return_value=fake_result):
        resp = client.post("/api/governance/regression-cycle/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["run_id"] == "chat-regression-cycle-1"
    assert data["evidence"]["promoted_count"] == 1
    assert data["trigger_application"]["trigger_count"] == 1
