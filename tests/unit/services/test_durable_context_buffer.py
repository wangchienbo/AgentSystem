from __future__ import annotations

from app.services.context_center import ContextCenter
from app.services.durable_context_buffer import DurableContextBuffer


def test_durable_context_buffer_persists_pending_events_across_instances(tmp_path) -> None:
    first = DurableContextBuffer.from_base_dir(tmp_path, max_events_per_session=5)
    first.append_pending_event(session_id="sess-1", event={"timestamp": "2026-05-04T17:00:00Z", "role": "user", "message": "hello"})
    first.append_pending_event(session_id="sess-1", event={"timestamp": "2026-05-04T17:00:01Z", "role": "system", "message": "pending"})

    second = DurableContextBuffer.from_base_dir(tmp_path, max_events_per_session=5)
    events = second.read_pending_events(session_id="sess-1")

    assert [item["message"] for item in events] == ["hello", "pending"]


def test_durable_context_buffer_bounds_session_history(tmp_path) -> None:
    buffer = DurableContextBuffer.from_base_dir(tmp_path, max_events_per_session=2)
    buffer.append_pending_event(session_id="sess-1", event={"timestamp": "1", "role": "user", "message": "m1"})
    buffer.append_pending_event(session_id="sess-1", event={"timestamp": "2", "role": "user", "message": "m2"})
    buffer.append_pending_event(session_id="sess-1", event={"timestamp": "3", "role": "user", "message": "m3"})

    events = buffer.read_pending_events(session_id="sess-1")
    assert [item["message"] for item in events] == ["m2", "m3"]


def test_context_center_exposes_session_aware_pending_buffer(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)
    center.append_pending_buffer_event("sess-a", {"timestamp": "2026-05-04T17:08:00Z", "role": "user", "message": "a1"})
    center.append_pending_buffer_event("sess-b", {"timestamp": "2026-05-04T17:08:10Z", "role": "user", "message": "b1"})
    center.append_pending_buffer_event("sess-a", {"timestamp": "2026-05-04T17:08:20Z", "role": "system", "message": "a2"})

    assert [item["message"] for item in center.read_pending_buffer_events("sess-a")] == ["a1", "a2"]
    assert [item["message"] for item in center.read_pending_buffer_events("sess-b")] == ["b1"]
