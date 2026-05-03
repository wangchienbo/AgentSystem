from __future__ import annotations

import asyncio

from app.models.chat import ChatMessageRequest
from app.models.pending_task import PendingTaskRecord
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
