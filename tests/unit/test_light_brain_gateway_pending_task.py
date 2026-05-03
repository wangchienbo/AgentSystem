from __future__ import annotations

import asyncio
from pathlib import Path

from app.models.chat import ChatMessageRequest
from app.models.pending_task import PendingTaskRecord
from app.persistence.runtime_state_store import RuntimeStateStore
from app.services.draft_app_service import DraftAppService
from app.services.light_brain_memory import LightBrainMemory
from app.system.gateway.light_brain_gateway import LightBrainGateway


class _Interpreter:
    def interpret(self, message, available_apps, user_id, session_id):
        from app.models.chat import InterpretedCommand

        return InterpretedCommand(intent="greet", raw_input=message, user_id=user_id)


class _PendingTaskStore:
    def __init__(self, task):
        self.task = task

    def get_latest_open_task(self, user_id):
        return self.task if user_id == "u1" else None


class _RecentWindow:
    def __init__(self):
        self.records = []


class _ContextCenter:
    def __init__(self):
        self.records = []

    def register_session_node(self, node):
        return None

    def get_recent_context(self, session_id, limit=100):
        return _RecentWindow()

    def read_linked_context(self, session_id, limit=50):
        return []

    def get_child_sessions(self, session_id):
        return []

    def append_context(self, record):
        self.records.append(record)


def test_gateway_appends_pending_task_note_to_context():
    memory = LightBrainMemory()
    context_center = _ContextCenter()
    task = PendingTaskRecord(
        task_id="pt-1",
        user_id="u1",
        intent="create_app",
        status="pending_input",
        target_ref={"target_id": "app_123"},
        missing_fields=["runtime_profile"],
    )
    gateway = LightBrainGateway(
        memory=memory,
        interpreter=_Interpreter(),
        context_center=context_center,
        pending_task_store=_PendingTaskStore(task),
    )

    response = asyncio.run(
        gateway.receive_message(
            ChatMessageRequest(user_id="u1", channel="test", message="继续")
        )
    )

    assert response.content
    note_contents = [record.content for record in context_center.records if record.role == "system"]
    assert any("pending_task task_id=pt-1" in content for content in note_contents)
    assert any("continuation_decision mode=continue_task" in content for content in note_contents)


def test_gateway_builds_draft_create_decision_without_pending_task():
    gateway = LightBrainGateway(memory=LightBrainMemory(), interpreter=_Interpreter())

    decision = gateway._build_continuation_decision("创建一个写代码 app", None)

    assert decision is not None
    assert decision.conversation_mode == "draft_create"
    assert decision.next_action["type"] == "create_draft_app"


def test_gateway_materializes_draft_app_and_pending_task(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
    )

    decision = gateway._build_continuation_decision("创建一个写代码 app", None)
    assert decision is not None
    gateway._materialize_continuation_decision(decision, user_id="u1", session_id="s1", message="创建一个写代码 app")

    assert decision.pending_task_id is not None
    assert decision.target_ref["app_id"].startswith("app_draft_")
    latest_task = pending_store.get_latest_open_task("u1")
    assert latest_task is not None
    assert latest_task.status == "drafted"
    assert latest_task.target_ref["app_id"] == decision.target_ref["app_id"]
    assert draft_service.get_app(decision.target_ref["app_id"]) is not None


def test_gateway_continue_task_returns_progress_response(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
    )

    create_decision = gateway._build_continuation_decision("创建一个写代码 app", None)
    assert create_decision is not None
    gateway._materialize_continuation_decision(create_decision, user_id="u1", session_id="s1", message="创建一个写代码 app")

    response = asyncio.run(
        gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1"))
    )

    assert response.type == "progress"
    assert "我已经恢复上次未完成的任务" in response.content
    assert response.requires_input is True
    assert response.data is not None
    assert response.data["pending_task"]["target_ref"]["app_id"].startswith("app_draft_")
