from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.system.invocation.tool_context_contract import ModelInvocationRecord, ToolContextQueryRequest, ToolContextQueryResponse

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
        self._asset_local_sessions: dict[tuple[str, str], str] = {}
        self._model_invocations: list[ModelInvocationRecord] = []

    # Chapter 5 target-shaped APIs -------------------------------------------------

    def get_recent_context(self, session_id: str, limit: int = 100) -> SessionContextWindow:
        return self.read_context(session_id, limit=limit)

    def get_context_range(self, session_id: str, start: int = 0, end: int | None = None) -> SessionContextWindow:
        records = self._records.get(session_id, [])
        sliced = records[start:end]
        return SessionContextWindow(session_id=session_id, records=sliced)

    def get_child_sessions(self, parent_session_id: str) -> list[SessionNode]:
        child_ids = [link.child_session_id for link in self._links if link.parent_session_id == parent_session_id]
        return [self._nodes[sid] for sid in child_ids if sid in self._nodes]

    def get_linked_sessions(self, session_id: str) -> list[SessionLink]:
        return self.list_links_for_session(session_id)

    def register_asset_local_session(self, asset_id: str, local_session_id: str, session_id: str | None = None) -> str:
        resolved_session_id = session_id or local_session_id
        self._asset_local_sessions[(asset_id, local_session_id)] = resolved_session_id
        return resolved_session_id

    def resolve_asset_local_session(self, asset_id: str, local_session_id: str) -> str | None:
        return self._asset_local_sessions.get((asset_id, local_session_id))

    def append_context_record(self, session_id: str, record: SessionContextRecord) -> SessionContextRecord:
        if record.session_id != session_id:
            record = SessionContextRecord(
                session_id=session_id,
                kind=record.kind,
                role=record.role,
                content=record.content,
                metadata=record.metadata,
            )
        return self.append_context(record)

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

    def list_sessions(self) -> list[SessionNode]:
        return list(self._nodes.values())

    def list_asset_local_sessions_for_session(self, session_id: str) -> list[dict[str, str]]:
        return [
            {"asset_id": asset_id, "local_session_id": local_session_id}
            for (asset_id, local_session_id), resolved in self._asset_local_sessions.items()
            if resolved == session_id
        ]

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

    def query_by_asset_local_session(self, asset_id: str, local_session_id: str, limit: int = 100) -> SessionContextWindow:
        session_id = self.resolve_asset_local_session(asset_id, local_session_id) or local_session_id
        return self.read_context(session_id, limit=limit)

    def query_recent_window(self, asset_id: str, local_session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        window = self.query_by_asset_local_session(asset_id, local_session_id, limit=limit)
        return [record.model_dump(mode="json") for record in window.records]

    def query_summary_records(self, asset_id: str, local_session_id: str, limit: int = 5) -> list[dict[str, Any]]:
        window = self.query_by_asset_local_session(asset_id, local_session_id, limit=200)
        records = [record for record in window.records if record.kind == "summary"]
        return [record.model_dump(mode="json") for record in records[-limit:]]

    def query_snapshot_record(self, asset_id: str, local_session_id: str) -> dict[str, Any] | None:
        window = self.query_by_asset_local_session(asset_id, local_session_id, limit=200)
        snapshot_candidates = [record for record in window.records if record.metadata.get("snapshot") is True]
        if not snapshot_candidates:
            return None
        return snapshot_candidates[-1].model_dump(mode="json")

    def query_evidence_refs(self, asset_id: str, local_session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        window = self.query_by_asset_local_session(asset_id, local_session_id, limit=200)
        evidence = [record for record in window.records if record.metadata.get("evidence_ref")]
        return [record.model_dump(mode="json") for record in evidence[-limit:]]

    def assemble_tool_context(self, request: ToolContextQueryRequest) -> ToolContextQueryResponse:
        request.validate()
        recent = self.query_recent_window(request.asset_id, request.local_session_id, limit=request.recent_limit)
        summaries = self.query_summary_records(request.asset_id, request.local_session_id) if request.include_summary else []
        snapshot = self.query_snapshot_record(request.asset_id, request.local_session_id) if request.include_snapshot else None
        evidence = self.query_evidence_refs(request.asset_id, request.local_session_id) if request.include_evidence_refs else []
        return ToolContextQueryResponse(
            asset_id=request.asset_id,
            local_session_id=request.local_session_id,
            recent_records=recent,
            summary_records=summaries,
            snapshot_record=snapshot,
            evidence_refs=evidence,
            trace_metadata={
                "purpose": request.purpose,
                "query": request.query,
                "recent_count": len(recent),
                "summary_count": len(summaries),
                "evidence_count": len(evidence),
            },
        )

    def record_model_invocation(self, record: ModelInvocationRecord) -> ModelInvocationRecord:
        self._model_invocations.append(record)
        return record

    def list_model_invocations(self, asset_id: str | None = None, local_session_id: str | None = None) -> list[dict[str, Any]]:
        items = self._model_invocations
        if asset_id is not None:
            items = [item for item in items if item.asset_id == asset_id]
        if local_session_id is not None:
            items = [item for item in items if item.local_session_id == local_session_id]
        return [item.to_dict() for item in items]
