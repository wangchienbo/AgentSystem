from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.context import SessionContextRecord, SessionContextWindow, SessionLink, SessionNode


class ContextCenter:
    """Phase H minimal context truth skeleton.

    This is a non-invasive standalone context store for session context body and
    session links. It does not yet replace LightBrainMemory in the active path,
    but establishes the target interface for the migration.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, SessionNode] = {}
        self._records: dict[str, list[SessionContextRecord]] = {}
        self._links: list[SessionLink] = []

    def register_session_node(self, node: SessionNode) -> SessionNode:
        now = datetime.now(UTC)
        existing = self._nodes.get(node.session_id)
        if existing is not None:
            existing.updated_at = now
            return existing
        node.updated_at = now
        if node.root_session_id is None:
            node.root_session_id = node.session_id if node.kind == "root" else node.parent_session_id
        self._nodes[node.session_id] = node
        self._records.setdefault(node.session_id, [])
        return node

    def get_session_node(self, session_id: str) -> SessionNode | None:
        return self._nodes.get(session_id)

    def append_context(self, record: SessionContextRecord) -> SessionContextRecord:
        self._records.setdefault(record.session_id, []).append(record)
        node = self._nodes.get(record.session_id)
        if node is not None:
            node.updated_at = datetime.now(UTC)
        return record

    def read_context(self, session_id: str, limit: int = 100) -> SessionContextWindow:
        records = self._records.get(session_id, [])
        return SessionContextWindow(session_id=session_id, records=records[-limit:])

    def link_sessions(self, link: SessionLink) -> SessionLink:
        self._links.append(link)
        child = self._nodes.get(link.child_session_id)
        if child is not None:
            child.parent_session_id = link.parent_session_id
            if child.root_session_id is None:
                parent = self._nodes.get(link.parent_session_id)
                child.root_session_id = parent.root_session_id if parent else link.parent_session_id
            child.updated_at = datetime.now(UTC)
        return link

    def list_links_for_session(self, session_id: str) -> list[SessionLink]:
        return [link for link in self._links if link.parent_session_id == session_id or link.child_session_id == session_id]

    def read_linked_context(self, session_id: str, limit: int = 100) -> dict[str, Any]:
        related_ids: set[str] = {session_id}
        for link in self.list_links_for_session(session_id):
            related_ids.add(link.parent_session_id)
            related_ids.add(link.child_session_id)
        return {
            sid: self.read_context(sid, limit=limit).model_dump(mode="json")
            for sid in sorted(related_ids)
        }
