from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from app.system.http_test_server import app, user_sessions, conversation_history, refinement_rollout, gateway


client = TestClient(app)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]



def test_login_accepts_json_payload_without_form_parser_dependency() -> None:
    user_sessions.clear()
    conversation_history.clear()

    response = client.post("/login", json={"username": "json_tester", "password": "ignored"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["session_id"] == "session_json_tester"
    assert data["username"] == "json_tester"
    assert "session_json_tester" in user_sessions


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


def test_api_chat_exposes_compatible_workflow_contract_metadata() -> None:
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
    from app.models.chat import ChatMessageResponse, ActionSuggestion

    fake_reply = ChatMessageResponse(
        type="progress",
        content="从上下文恢复继续执行。",
        session_id="session_tester",
        data={
            "pending_task": {"task_id": "pt-ctx-1"},
            "continuation_decision": {"conversation_mode": "continue_task"},
            "context_view": {"stable_count": 2, "pending_count": 1},
        },
    )

    with patch("app.system.http_test_server.gateway.receive_message", new=AsyncMock(return_value=fake_reply)):
        response = client.post("/api/chat", json={"message": "继续"})

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["pending_task"]["task_id"] == "pt-ctx-1"
    assert data["workflow_contract"]["continuation_decision"]["conversation_mode"] == "continue_task"
    assert data["context_view"] == {"stable_count": 2, "pending_count": 1}


def test_api_chat_exposes_recent_working_memory_view() -> None:
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

    fake_reply = ChatMessageResponse(
        type="progress",
        content="从最近工作记忆继续。",
        session_id="session_tester",
        data={
            "continuation_decision": {"conversation_mode": "continue_task"},
            "context_view": {
                "stable": [{"id": "detail:session_tester:1", "message": "stable-a"}],
                "pending": [{"message": "pending-a"}],
            },
        },
    )

    with patch("app.system.http_test_server.gateway.receive_message", new=AsyncMock(return_value=fake_reply)):
        response = client.post("/api/chat", json={"message": "继续"})

    assert response.status_code == 200
    data = response.json()
    assert data["context_view"]["stable"][0]["message"] == "stable-a"
    assert data["context_view"]["pending"][0]["message"] == "pending-a"


def test_api_action_exposes_compatible_workflow_contract_metadata() -> None:
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

    fake_reply = ChatMessageResponse(
        type="progress",
        content="动作执行已接续。",
        session_id="session_tester",
        data={
            "pending_task": {"task_id": "pt-action-1"},
            "continuation_decision": {"conversation_mode": "continue_task"},
        },
    )

    with patch("app.system.http_test_server.gateway.execute_action", new=AsyncMock(return_value=fake_reply)):
        response = client.post(
            "/api/action",
            json={"action_id": "continue:pt-action-1", "action_params": {}},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_contract"]["pending_task"]["task_id"] == "pt-action-1"
    assert data["workflow_contract"]["continuation_decision"]["conversation_mode"] == "continue_task"


def test_api_action_exposes_implementation_and_acceptance_payloads() -> None:
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

    fake_reply = ChatMessageResponse(
        type="progress",
        content="workflow action executed",
        session_id="session_tester",
        data={
            "pending_task": {"task_id": "pt-exec-1", "next_recommended_action": {"type": "run_acceptance"}},
            "implementation_plan": {"target_files": ["app/system/gateway/light_brain_gateway.py"]},
            "acceptance_plan": {"test_probe_commands": ["pytest tests/unit/test_light_brain_gateway_pending_task.py -q"]},
            "acceptance_result": {"status": "passed"},
            "context_view": {"stable": [], "pending": []},
        },
    )

    with patch("app.system.http_test_server.gateway.execute_action", new=AsyncMock(return_value=fake_reply)):
        response = client.post(
            "/api/action",
            json={"action_id": "workflow-action:run_acceptance:app_demo", "action_params": {"intent": "run_acceptance", "app_id": "app_demo"}},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["implementation_plan"]["target_files"] == ["app/system/gateway/light_brain_gateway.py"]
    assert data["data"]["acceptance_result"]["status"] == "passed"
    assert data["context_view"] == {"stable": [], "pending": []}


def test_api_action_runs_real_executable_workflow_chain(tmp_path) -> None:
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

    from app.models.pending_task import PendingTaskRecord
    from app.persistence.runtime_state_store import RuntimeStateStore
    from app.system.runtime.pending_task_store import PendingTaskStore

    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    original_store = getattr(gateway, "_pending_task_store", None)
    gateway._pending_task_store = store
    try:
        task = PendingTaskRecord(
            task_id="pt-http-chain-1",
            user_id="tester",
            session_id="session_tester",
            intent="create_app",
            status="ready_to_execute",
            current_stage="tasklist_preparing",
            stage_status="in_progress",
            target_ref={"app_id": "app_http_chain"},
            draft_payload={"name": "http_chain_demo"},
            next_recommended_action={"type": "materialize_task_list", "app_id": "app_http_chain"},
        )
        store.upsert_task(task)

        response = client.post(
            "/api/action",
            json={"action_id": "workflow-action:materialize_task_list:app_http_chain", "action_params": {"intent": "materialize_task_list", "app_id": "app_http_chain"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["task_list"]) == 3
        assert data["workflow_contract"]["pending_task"]["current_stage"] == "repo_locating"
        assert data["actions"][0]["payload"]["intent"] == "locate_repo_context"
    finally:
        gateway._pending_task_store = original_store


def test_api_action_runs_real_repo_to_implementation_chain(tmp_path) -> None:
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

    from app.models.pending_task import PendingTaskRecord
    from app.persistence.runtime_state_store import RuntimeStateStore
    from app.system.runtime.pending_task_store import PendingTaskStore

    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    original_store = getattr(gateway, "_pending_task_store", None)
    gateway._pending_task_store = store
    try:
        task = PendingTaskRecord(
            task_id="pt-http-chain-2",
            user_id="tester",
            session_id="session_tester",
            intent="create_app",
            status="ready_to_execute",
            current_stage="repo_locating",
            stage_status="in_progress",
            target_ref={"app_id": "app_http_chain_2"},
            task_list=[{"id": "t1", "module": "app/system/gateway/light_brain_gateway.py"}],
            next_recommended_action={"type": "locate_repo_context", "app_id": "app_http_chain_2"},
        )
        store.upsert_task(task)

        repo_response = client.post(
            "/api/action",
            json={"action_id": "workflow-action:locate_repo_context:app_http_chain_2", "action_params": {"intent": "locate_repo_context", "app_id": "app_http_chain_2"}},
        )
        assert repo_response.status_code == 200
        repo_data = repo_response.json()
        assert repo_data["data"]["repo_context"]["active_repo_path"] == str(REPO_ROOT)
        assert repo_data["data"]["repo_context"]["repo_valid"] is True
        assert "git_branch" in repo_data["data"]["repo_context"]
        assert repo_data["actions"][0]["payload"]["intent"] == "implement_app_change"

        impl_response = client.post(
            "/api/action",
            json={"action_id": "workflow-action:implement_app_change:app_http_chain_2", "action_params": {"intent": "implement_app_change", "app_id": "app_http_chain_2"}},
        )
        assert impl_response.status_code == 200
        impl_data = impl_response.json()
        assert impl_data["data"]["implementation_plan"]["target_files"] == ["app/system/gateway/light_brain_gateway.py"]
        assert impl_data["data"]["implementation_plan"]["validation_map"][0]["probe"] == "pytest tests/unit/test_light_brain_gateway_pending_task.py -q"
        assert impl_data["data"]["implementation_plan"]["changed_files_intent"][0]["mapped_work_item_id"] == "work-1"
        assert impl_data["actions"][0]["payload"]["intent"] == "run_acceptance"
    finally:
        gateway._pending_task_store = original_store


def test_api_action_runs_real_implementation_to_acceptance_chain(tmp_path) -> None:
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

    from app.models.pending_task import PendingTaskRecord
    from app.persistence.runtime_state_store import RuntimeStateStore
    from app.system.runtime.pending_task_store import PendingTaskStore

    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    original_store = getattr(gateway, "_pending_task_store", None)
    gateway._pending_task_store = store
    try:
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        task = PendingTaskRecord(
            task_id="pt-http-chain-3",
            user_id="tester",
            session_id="session_tester",
            intent="create_app",
            status="ready_to_execute",
            current_stage="implementation_pending",
            stage_status="in_progress",
            target_ref={"app_id": "app_http_chain_3"},
            repo_context={
                "active_repo_path": str(repo_root),
                "primary_readme_path": str(repo_root / "README.md"),
                "key_docs": [],
                "target_modules": ["app/system/gateway/light_brain_gateway.py"],
            },
            acceptance_plan={
                "test_probe_commands": ["python3 -c 'print(\"ok\")'"],
                "http_runtime_verification_points": [],
                "success_criteria": ["command exits 0"],
                "results": [],
            },
            next_recommended_action={"type": "implement_app_change", "app_id": "app_http_chain_3"},
        )
        store.upsert_task(task)

        impl_response = client.post(
            "/api/action",
            json={"action_id": "workflow-action:implement_app_change:app_http_chain_3", "action_params": {"intent": "implement_app_change", "app_id": "app_http_chain_3"}},
        )
        assert impl_response.status_code == 200
        impl_data = impl_response.json()
        assert impl_data["actions"][0]["payload"]["intent"] == "run_acceptance"

        acceptance_response = client.post(
            "/api/action",
            json={"action_id": "workflow-action:run_acceptance:app_http_chain_3", "action_params": {"intent": "run_acceptance", "app_id": "app_http_chain_3"}},
        )
        assert acceptance_response.status_code == 200
        acceptance_data = acceptance_response.json()
        assert acceptance_data["data"]["acceptance_result"]["status"] == "passed"
        assert acceptance_data["data"]["acceptance_result"]["evidence"]["summary"]["passed_count"] == 1
        assert acceptance_data["data"]["acceptance_result"]["evidence"]["commands"][0]["matched_success_criteria"] == ["command exits 0"]
        assert acceptance_data["data"]["acceptance_result"]["evidence"]["commands"][0]["matched_work_item_ids"] == ["work-1"]
        assert acceptance_data["workflow_contract"]["pending_task"]["current_stage"] == "done"
    finally:
        gateway._pending_task_store = original_store


def test_api_chat_exposes_gateway_action_contract() -> None:
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
    from app.models.chat import ChatMessageResponse, ActionSuggestion

    fake_reply = ChatMessageResponse(
        type="progress",
        content="草稿 app 已准备好正式接入。",
        session_id="session_tester",
        data={
            "pending_task": {
                "task_id": "task-draft-1",
                "target_ref": {"app_id": "app_draft_demo"},
                "next_recommended_action": {"type": "apply_draft_app", "app_id": "app_draft_demo"},
            },
            "lifecycle_handoff": {
                "recommended_intent": "apply_draft_app",
                "target_app_id": "app_draft_demo",
            },
        },
        actions=[
            ActionSuggestion(
                id="apply-draft:app_draft_demo",
                label="正式启用这个 app",
                action_type="execute",
                payload={"intent": "apply_draft_app", "app_id": "app_draft_demo"},
                style="primary",
            )
        ],
        related_app="app_draft_demo",
    )

    with patch("app.system.http_test_server.gateway.receive_message", new=AsyncMock(return_value=fake_reply)):
        response = client.post("/api/chat", json={"message": "继续"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["lifecycle_handoff"]["recommended_intent"] == "apply_draft_app"
    assert data["actions"][0]["payload"] == {"intent": "apply_draft_app", "app_id": "app_draft_demo"}
    assert data["related_app"] == "app_draft_demo"
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

    regression_dir = REPO_ROOT / "data/chat_regression"
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

    regression_dir = REPO_ROOT / "data/chat_regression"
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




def test_api_action_executes_real_apply_draft_app_path() -> None:
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
    from app.models.chat import ChatMessageResponse, ActionSuggestion

    fake_reply = ChatMessageResponse(
        type="progress",
        content="已把 draft app 接入正式生命周期，并推进到可运行状态。",
        session_id="session_tester",
        data={
            "app_id": "app_draft_demo",
            "app_status": "running",
            "source": "DraftAppApplicationService",
            "lifecycle_transition": "draft_to_running_activation",
        },
        actions=[
            ActionSuggestion(
                id="query_status",
                label="查看状态",
                action_type="execute",
                payload={"intent": "query_app", "target": "app_draft_demo"},
                style="secondary",
            )
        ],
        related_app="app_draft_demo",
    )

    with patch("app.system.http_test_server.gateway.execute_action", new=AsyncMock(return_value=fake_reply)) as mocked_execute:
        response = client.post(
            "/api/action",
            json={
                "action_id": "apply-draft:app_draft_demo",
                "action_params": {"intent": "apply_draft_app", "app_id": "app_draft_demo"},
            },
        )

    assert mocked_execute.await_count == 1
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["lifecycle_transition"] == "draft_to_running_activation"
    assert data["related_app"] == "app_draft_demo"
    assert data["actions"][0]["payload"] == {"intent": "query_app", "target": "app_draft_demo"}
    assert conversation_history["session_tester"][-1]["content"] == "已把 draft app 接入正式生命周期，并推进到可运行状态。"
    mocked_execute.assert_awaited_once_with(
        user_id="tester",
        session_id="session_tester",
        action_id="apply-draft:app_draft_demo",
        action_params={"intent": "apply_draft_app", "app_id": "app_draft_demo"},
    )
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

    client.post("/api/governance/regression-cycle/nightly?interval_seconds=3600")

    not_due_resp = client.post("/api/governance/regression-cycle/nightly/tick")
    assert not_due_resp.status_code == 200
    not_due_data = not_due_resp.json()
    assert not_due_data["success"] is True
    assert not_due_data["triggered"] is False
    assert "due_now" in not_due_data["nightly_status"]
    assert not_due_data["nightly_status"]["last_tick_decision"] == "skipped_not_due"

    import app.system.http_test_server as server
    schedule = server.runtime_services["scheduler"].get_schedule("sch.regression.governance.nightly")
    from datetime import UTC, datetime, timedelta
    schedule.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)

    from unittest.mock import patch
    fake_cycle = {
        "run_id": "nightly-run-due",
        "summary": {"topic_count": 4},
        "path": "/tmp/nightly-run-due.jsonl",
        "evidence": {"promoted_count": 1},
        "trigger_application": {"trigger_count": 1},
    }
    with patch("app.system.http_test_server.regression_nightly_control.run_cycle", return_value=fake_cycle):
        due_resp = client.post("/api/governance/regression-cycle/nightly/tick")

    assert due_resp.status_code == 200
    due_data = due_resp.json()
    assert due_data["success"] is True
    assert due_data["triggered"] is True
    assert due_data["cycle"]["run_id"] == "nightly-run-due"
    assert due_data["nightly_status"]["last_tick_decision"] == "triggered_due"
    assert due_data["nightly_status"]["last_cycle_result"]["run_id"] == "nightly-run-due"


def test_api_governance_regression_cycle_nightly_driver_controls() -> None:
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

    import app.system.http_test_server as server
    server.regression_nightly_driver.stop()

    status_resp = client.get("/api/governance/regression-cycle/nightly/driver")
    assert status_resp.status_code == 200
    assert status_resp.json()["driver"]["running"] is False

    start_resp = client.post("/api/governance/regression-cycle/nightly/driver/start?interval_seconds=5")
    assert start_resp.status_code == 200
    assert start_resp.json()["driver"]["interval_seconds"] == 5
    assert start_resp.json()["driver"]["persisted_running"] is True

    stop_resp = client.post("/api/governance/regression-cycle/nightly/driver/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["driver"]["running"] is False
    assert stop_resp.json()["driver"]["persisted_running"] is False


def test_api_governance_nightly_status_includes_driver_state() -> None:
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

    client.post("/api/governance/regression-cycle/nightly/driver/start?interval_seconds=5")
    status_resp = client.get("/api/governance/regression-cycle/nightly")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["schedules"] is not None

    dash_resp = client.get("/api/governance/regression-dashboard")
    assert dash_resp.status_code == 200
    dash_data = dash_resp.json()
    assert "driver" in dash_data["nightly_automation"]

    client.post("/api/governance/regression-cycle/nightly/driver/stop")


def test_nightly_tick_uses_service_session_identity() -> None:
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

    import app.system.http_test_server as server
    service_session = server.ensure_regression_service_session()
    assert service_session == "session_regression_nightly_service"
    assert service_session in user_sessions


def test_governance_dashboard_exposes_automation_control_card() -> None:
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

    resp = client.get("/api/governance/regression-dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "automation_control" in data["nightly_automation"]
    assert "driver" in data["nightly_automation"]["automation_control"]


def test_api_governance_regression_cycle_nightly_trigger_can_auto_apply_governance() -> None:
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

    fake_cycle = {
        "run_id": "nightly-run-1",
        "summary": {"topic_count": 4},
        "path": "/tmp/nightly-run-1.jsonl",
        "evidence": {"promoted_count": 1},
        "trigger_application": {"trigger_count": 1},
    }
    fake_result = {
        "triggered": True,
        "schedule_results": [],
        "cycle": fake_cycle,
        "governance_rollout": {
            "applied": True,
            "queue_id": "q-primary",
            "item": {"status": "applied"},
        },
    }
    with patch("app.system.http_test_server.regression_nightly_control.trigger_manual_cycle", return_value=fake_result) as mocked:
        resp = client.post("/api/governance/regression-cycle/nightly/trigger?auto_apply_governance=true")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["governance_rollout"]["applied"] is True
    assert data["governance_rollout_summary"] == {
        "decision": "auto_applied",
        "action": "applied_selected_queue",
        "queue_id": "q-primary",
        "applied": True,
        "reason": None,
        "review_scope": None,
        "review_reason": None,
        "decision_code": None,
        "decision_label": None,
        "render_badge": None,
        "render_operator_note": None,
    }
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["auto_apply_governance"] is True


def test_api_governance_regression_cycle_nightly_trigger_returns_preflight_block() -> None:
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

    fake_cycle = {
        "run_id": "nightly-run-1",
        "summary": {"topic_count": 4},
        "path": "/tmp/nightly-run-1.jsonl",
        "evidence": {"promoted_count": 1},
        "trigger_application": {"trigger_count": 1},
    }
    fake_result = {
        "triggered": True,
        "schedule_results": [],
        "cycle": fake_cycle,
        "governance_rollout": {
            "applied": False,
            "reason": "secondary_requires_review",
            "preflight": {"can_apply": False, "hold_reason": "secondary_requires_review", "review_scope": "operator_review_required", "review_reason": "priority_secondary"},
        },
    }
    with patch("app.system.http_test_server.regression_nightly_control.trigger_manual_cycle", return_value=fake_result):
        resp = client.post("/api/governance/regression-cycle/nightly/trigger?auto_apply_governance=true")

    assert resp.status_code == 200
    data = resp.json()
    assert data["governance_rollout"]["applied"] is False
    assert data["governance_rollout"]["preflight"]["hold_reason"] == "secondary_requires_review"
    assert data["governance_rollout_summary"] == {
        "decision": "held",
        "action": "operator_review_required",
        "queue_id": None,
        "applied": False,
        "reason": "secondary_requires_review",
        "review_scope": "operator_review_required",
        "review_reason": "priority_secondary",
        "decision_code": None,
        "decision_label": None,
        "render_badge": None,
        "render_operator_note": None,
    }


def test_governance_nightly_trigger_contract_keeps_cycle_and_rollout_fields_together() -> None:
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
        "triggered": True,
        "schedule_results": [],
        "cycle": {
            "run_id": "nightly-run-contract",
            "summary": {"topic_count": 4},
            "path": "/tmp/nightly-run-contract.jsonl",
            "evidence": {"promoted_count": 1},
            "trigger_application": {"trigger_count": 1},
        },
        "governance_rollout": {
            "applied": True,
            "queue_id": "q-primary",
            "preflight": {
                "can_apply": True,
                "hold_reason": "none",
                "matched_stage": "tier_gate",
                "decision_code": "tier.primary_auto_apply",
                "decision_label": "Primary tier auto-apply allowed",
                "review_scope": "light_auto_apply_ok",
                "review_reason": "primary_selection_healthy",
                "render_badge": "AUTO | Primary tier auto-apply allowed",
                "render_operator_note": "AUTO | Primary tier auto-apply allowed | code=tier.primary_auto_apply | stage=tier_gate | scope=light_auto_apply_ok | risk=medium | queue=q-primary",
            },
            "item": {"status": "applied"},
        },
        "governance_rollout_summary": {
            "decision": "auto_applied",
            "action": "applied_selected_queue",
            "queue_id": "q-primary",
            "applied": True,
            "reason": None,
            "review_scope": "light_auto_apply_ok",
            "review_reason": "primary_selection_healthy",
            "decision_code": "tier.primary_auto_apply",
            "decision_label": "Primary tier auto-apply allowed",
            "render_badge": "AUTO | Primary tier auto-apply allowed",
            "render_operator_note": "AUTO | Primary tier auto-apply allowed | code=tier.primary_auto_apply | stage=tier_gate | scope=light_auto_apply_ok | risk=medium | queue=q-primary",
        },
    }
    with patch("app.system.http_test_server.regression_nightly_control.trigger_manual_cycle", return_value=fake_result):
        resp = client.post("/api/governance/regression-cycle/nightly/trigger?auto_apply_governance=true")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["triggered"] is True
    assert data["cycle"]["run_id"] == "nightly-run-contract"
    assert data["cycle"]["trigger_application"]["trigger_count"] == 1
    assert data["governance_rollout"]["applied"] is True
    assert data["governance_rollout_summary"]["decision"] == "auto_applied"
    assert data["governance_rollout_summary"]["decision_code"] == "tier.primary_auto_apply"
    assert data["governance_rollout"]["preflight"]["can_apply"] is True
    assert data["governance_rollout"]["preflight"]["render_badge"] == "AUTO | Primary tier auto-apply allowed"
    assert "code=tier.primary_auto_apply" in data["governance_rollout"]["preflight"]["render_operator_note"]



def test_api_chat_persists_live_chat_observation() -> None:
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

    with patch("app.system.http_test_server.gateway.receive_message", new=AsyncMock(return_value=fake_reply)),          patch("app.system.http_test_server.persist_chat_observation") as persist_mock:
        response = client.post("/api/chat", json={"message": "帮我确认这个接口行为"})

    assert response.status_code == 200
    assert persist_mock.call_count == 1
    probe = persist_mock.call_args.kwargs["probe"]
    assert probe["source"] == "live_chat_request"
    assert probe["topic"] == "api"
    assert probe["answer_mode"] == "verification_required"
    assert probe["fallback_like"] is True

