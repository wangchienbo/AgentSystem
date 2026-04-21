from __future__ import annotations

from app.models.context import SessionContextRecord, SessionLink, SessionNode
from app.services.context_center import ContextCenter


class TestContextCenter:
    def test_register_session_node_and_append_context(self):
        center = ContextCenter()
        center.register_session_node(
            SessionNode(session_id="sess-root", user_id="u1", channel="webchat", kind="root")
        )
        center.append_context(
            SessionContextRecord(session_id="sess-root", kind="message", role="user", content="你好")
        )

        window = center.read_context("sess-root")
        assert window.session_id == "sess-root"
        assert len(window.records) == 1
        assert window.records[0].content == "你好"

    def test_link_sessions_and_read_linked_context(self):
        center = ContextCenter()
        center.register_session_node(
            SessionNode(session_id="sess-root", user_id="u1", channel="webchat", kind="root")
        )
        center.register_session_node(
            SessionNode(
                session_id="sess-child",
                user_id="u1",
                channel="webchat",
                kind="child",
                parent_session_id="sess-root",
            )
        )
        center.append_context(
            SessionContextRecord(session_id="sess-root", kind="message", role="user", content="root-msg")
        )
        center.append_context(
            SessionContextRecord(session_id="sess-child", kind="message", role="assistant", content="child-msg")
        )
        center.link_sessions(
            SessionLink(parent_session_id="sess-root", child_session_id="sess-child", link_type="child")
        )

        linked = center.read_linked_context("sess-root")
        assert "sess-root" in linked
        assert "sess-child" in linked
        assert linked["sess-child"]["records"][0]["content"] == "child-msg"
