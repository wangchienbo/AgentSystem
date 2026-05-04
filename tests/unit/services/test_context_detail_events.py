from __future__ import annotations

from datetime import UTC, datetime

from app.models.context import SessionContextRecord
from app.services.context_center import ContextCenter
from app.services.context_query_service import ContextQueryService
from app.services.context_writer import ContextWriter


def test_context_writer_persists_minimal_detail_event_schema(tmp_path) -> None:
    writer = ContextWriter.from_base_dir(tmp_path)
    timestamp = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)

    writer.append_detail_event(session_id="sess-1", role="tool.read_file", message="payload", timestamp=timestamp)
    event_path = tmp_path / "detail" / "sess-1" / "2026-05-04.jsonl"

    assert event_path.exists()
    line = event_path.read_text(encoding="utf-8").strip()
    assert '"role": "tool.read_file"' in line
    assert '"message": "payload"' in line
    assert 'record_id' not in line
    assert 'metadata' not in line


def test_context_query_service_reads_minimal_detail_events(tmp_path) -> None:
    writer = ContextWriter.from_base_dir(tmp_path)
    writer.append_detail_event(session_id="sess-1", role="user", message="hello")
    writer.append_detail_event(session_id="sess-1", role="asset.demo", message="world")

    query = ContextQueryService.from_base_dir(tmp_path)
    events = query.read_detail_events(session_id="sess-1")

    assert [item.role for item in events] == ["user", "asset.demo"]
    assert [item.message for item in events] == ["hello", "world"]


def test_context_center_mirrors_non_summary_records_to_detail_store(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)
    center.append_context(SessionContextRecord(session_id="sess-1", kind="message", role="user", content="hello"))
    center.append_context(SessionContextRecord(session_id="sess-1", kind="system_note", role="system", content="note"))
    center.append_context(SessionContextRecord(session_id="sess-1", kind="summary", role="system", content="summary"))

    events = center.read_detail_events("sess-1")

    assert [item.role for item in events] == ["user", "system"]
    assert [item.message for item in events] == ["hello", "note"]
