from __future__ import annotations

from app.models.context import SessionContextRecord, SessionNode
from app.services.context_center import ContextCenter


class _GatewayLikeConsumer:
    def __init__(self, center: ContextCenter) -> None:
        self.center = center

    def fetch_summary_view(self, session_id: str):
        return self.center.get_recent_working_memory_summaries(session_id, limit=5)

    def fetch_detail(self, session_id: str, ref_id: str):
        return self.center.get_detail_record_by_reference(session_id, ref_id)


class _RuntimeLikeConsumer:
    def __init__(self, center: ContextCenter) -> None:
        self.center = center

    def assemble_recent_view(self, session_id: str):
        return self.center.get_recent_working_memory_view(session_id, limit=300)


def test_summary_and_detail_retrieval_are_callable_from_gateway_runtime_layers(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)
    center.register_session_node(SessionNode(session_id="sess-1", user_id="u1", channel="test"))
    center.append_context_record("sess-1", SessionContextRecord(session_id="sess-1", kind="message", role="user", content="hello"))
    center.append_context_record("sess-1", SessionContextRecord(session_id="sess-1", kind="system_note", role="system", content="note"))
    center.enqueue_summary_write("sess-1", "final-summary", replace=True)

    gateway = _GatewayLikeConsumer(center)
    runtime = _RuntimeLikeConsumer(center)

    recent = runtime.assemble_recent_view("sess-1")
    summaries = gateway.fetch_summary_view("sess-1")
    detail = gateway.fetch_detail("sess-1", recent["stable"][0]["id"])

    assert summaries[-1]["message"] == "final-summary"
    assert detail is not None and detail["message"] == "hello"
    assert recent["pending"] == []
