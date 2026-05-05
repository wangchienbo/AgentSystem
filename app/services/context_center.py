from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.context_storage_paths import (
    DEFAULT_CONTEXT_CENTER_DIR,
)
from app.system.invocation.tool_context_contract import ModelInvocationRecord, ToolContextQueryRequest, ToolContextQueryResponse

from app.models.context import SessionContextRecord, SessionContextWindow, SessionLink, SessionNode
from app.services.context_query_service import ContextQueryService
from app.services.context_recovery_manager import ContextRecoveryManager
from app.services.context_reorder_window import SessionLocalReorderWindow
from app.services.context_summary_worker import ContextSummaryWorker
from app.services.context_writer import ContextWriter
from app.services.durable_context_buffer import DurableContextBuffer


class ContextCenter:
    """Phase H minimal context truth skeleton.

    This is a non-invasive standalone context store for session context body and
    session links. It does not yet replace LightBrainMemory in the active path,
    but establishes the target interface for the migration.
    """

    def __init__(self, *, base_dir: str | Path = DEFAULT_CONTEXT_CENTER_DIR) -> None:
        self._nodes: dict[str, SessionNode] = {}
        self._records: dict[str, list[SessionContextRecord]] = {}
        self._links: list[SessionLink] = []
        self._asset_local_sessions: dict[tuple[str, str], str] = {}
        self._model_invocations: list[ModelInvocationRecord] = []
        self._base_dir = Path(base_dir)
        self._writer = ContextWriter.from_base_dir(self._base_dir)
        self._query_service = ContextQueryService.from_base_dir(self._base_dir)
        self._recovery_manager = ContextRecoveryManager.from_base_dir(self._base_dir)
        self._summary_worker = ContextSummaryWorker.from_base_dir(self._base_dir)
        self._durable_buffer = DurableContextBuffer.from_base_dir(self._base_dir)
        self._reorder_window = SessionLocalReorderWindow()
        self._startup_recovery_result = self._recovery_manager.recover_pending_sessions(
            buffer_dir=self._durable_buffer.paths.buffer_dir,
            flush_session=self.flush_stable_pending_events,
        )

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
        if record.kind == "summary":
            self._writer.append_summary_event(
                session_id=record.session_id,
                role=record.role,
                message=record.content,
                timestamp=record.created_at,
            )
        else:
            self._writer.append_detail_event(
                session_id=record.session_id,
                role=record.role,
                message=record.content,
                timestamp=record.created_at,
            )
            self._write_provisional_summary(
                session_id=record.session_id,
                role="system",
                message=self._build_provisional_summary(record.role, record.content),
                timestamp=record.created_at,
            )
        node = self._nodes.get(record.session_id)
        if node is not None:
            node.updated_at = datetime.now(UTC)
        return record

    def read_detail_events(self, session_id: str, limit: int = 100):
        return self._query_service.read_detail_events(session_id=session_id, limit=limit)

    def read_summary_events(self, session_id: str, limit: int = 100):
        return self._query_service.read_summary_events(session_id=session_id, limit=limit)

    def enqueue_summary_write(self, session_id: str, summary_text: str, *, role: str = "system", replace: bool = True) -> dict[str, Any]:
        return self._summary_worker.enqueue_summary_write(session_id=session_id, summary_text=summary_text, role=role, replace=replace)

    def append_pending_buffer_event(self, session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        stored = self._durable_buffer.append_pending_event(session_id=session_id, event=event)
        self.flush_stable_pending_events(session_id)
        return stored

    def read_pending_buffer_events(self, session_id: str):
        return self._durable_buffer.read_pending_events(session_id=session_id)

    def get_recent_working_memory_view(self, session_id: str, limit: int = 300) -> dict[str, Any]:
        stable_events = self.read_detail_events(session_id, limit=limit)
        pending_events = self.read_pending_buffer_events(session_id)
        return {
            "session_id": session_id,
            "stable": [
                {
                    "id": f"detail:{session_id}:{index}",
                    "timestamp": item.timestamp.isoformat().replace("+00:00", "Z"),
                    "role": item.role,
                    "message": item.message,
                }
                for index, item in enumerate(stable_events[-limit:], start=max(1, len(stable_events[-limit:]) * 0 + 1))
            ],
            "pending": list(pending_events)[-limit:],
        }

    def get_recent_working_memory_summaries(self, session_id: str, limit: int = 5) -> list[dict[str, Any]]:
        return [
            {
                "id": f"summary:{session_id}:{index}",
                "timestamp": item.timestamp.isoformat().replace("+00:00", "Z"),
                "role": item.role,
                "message": item.message,
            }
            for index, item in enumerate(self.read_summary_events(session_id, limit=limit), start=1)
        ]

    def get_detail_record_by_reference(self, session_id: str, reference_id: str) -> dict[str, Any] | None:
        if not reference_id.startswith(f"detail:{session_id}:"):
            return None
        try:
            index = int(reference_id.rsplit(":", 1)[-1]) - 1
        except ValueError:
            return None
        stable = self.get_recent_working_memory_view(session_id, limit=300)["stable"]
        if index < 0 or index >= len(stable):
            return None
        return stable[index]

    def flush_stable_pending_events(self, session_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        pending = self._durable_buffer.read_pending_events(session_id=session_id)
        if not pending:
            return {
                "flushed_count": 0,
                "waiting_count": 0,
            }
        result = self._reorder_window.rebalance(pending, now=now)
        for event in result.stable_events:
            event_timestamp = datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
            event_role = str(event.get("role") or "system")
            event_message = str(event.get("message") or "")
            self._writer.append_detail_event(
                session_id=session_id,
                role=event_role,
                message=event_message,
                timestamp=event_timestamp,
            )
            self._write_provisional_summary(
                session_id=session_id,
                role="system",
                message=self._build_provisional_summary(event_role, event_message),
                timestamp=event_timestamp,
            )
        self._durable_buffer.replace_pending_events(session_id=session_id, events=result.waiting_events)
        return {
            "flushed_count": len(result.stable_events),
            "waiting_count": len(result.waiting_events),
        }

    @property
    def startup_recovery_result(self) -> dict[str, Any]:
        return dict(self._startup_recovery_result)

    def _build_provisional_summary(self, role: str, message: str) -> str:
        compact = " ".join(message.split())
        if len(compact) > 120:
            compact = compact[:117] + "..."
        return f"[{role}] {compact}" if compact else f"[{role}]"

    def _write_provisional_summary(self, *, session_id: str, role: str, message: str, timestamp: datetime) -> None:
        self._writer.append_summary_event(
            session_id=session_id,
            role=role,
            message=message,
            timestamp=timestamp,
        )

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
        session_id = self.resolve_asset_local_session(asset_id, local_session_id) or local_session_id
        summary_events = self.read_summary_events(session_id, limit=limit)
        if summary_events:
            latest = summary_events[-1]
            return [
                {
                    "session_id": session_id,
                    "kind": "summary",
                    "role": latest.role,
                    "content": latest.message,
                    "created_at": latest.timestamp.isoformat().replace("+00:00", "Z"),
                    "metadata": {"source": "summary_store", "view": "stable", "replacement": True},
                }
            ]
        window = self.query_by_asset_local_session(asset_id, local_session_id, limit=200)
        records = [record for record in window.records if record.kind == "summary"]
        return [record.model_dump(mode="json") for record in records[-1:]]

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
