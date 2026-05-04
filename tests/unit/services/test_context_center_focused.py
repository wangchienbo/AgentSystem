from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.context import SessionContextRecord
from app.services.context_center import ContextCenter
from app.services.context_recovery_manager import ContextRecoveryManager
from app.services.context_storage_paths import build_context_storage_paths
from app.services.context_summary_worker import ContextSummaryWorker
from app.services.durable_context_buffer import DurableContextBuffer


def test_context_storage_path_helpers_build_expected_directories(tmp_path) -> None:
    paths = build_context_storage_paths(tmp_path)

    assert paths.base_dir == tmp_path
    assert paths.detail_dir == tmp_path / "detail"
    assert paths.summary_dir == tmp_path / "summary"
    assert paths.buffer_dir == tmp_path / "buffer"


def test_context_center_recent_working_memory_merge_exposes_reference_lookup(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)
    center.append_context_record("sess-1", SessionContextRecord(session_id="sess-1", kind="message", role="user", content="stable-1"))
    center.append_context_record("sess-1", SessionContextRecord(session_id="sess-1", kind="system_note", role="system", content="stable-2"))
    center.append_pending_buffer_event("sess-1", {"timestamp": "2099-05-04T18:00:00Z", "role": "assistant", "message": "pending-1"})

    view = center.get_recent_working_memory_view("sess-1", limit=10)
    resolved = center.get_detail_record_by_reference("sess-1", view["stable"][1]["id"])

    assert [item["message"] for item in view["stable"]] == ["stable-1", "stable-2"]
    assert [item["message"] for item in view["pending"]] == ["pending-1"]
    assert resolved is not None
    assert resolved["message"] == "stable-2"


def test_context_center_startup_recovery_flushes_only_stable_pending_events(tmp_path) -> None:
    base_now = datetime.now(UTC).replace(microsecond=0)
    stable_ts = (base_now - timedelta(minutes=8)).isoformat().replace("+00:00", "Z")
    waiting_ts = (base_now - timedelta(seconds=15)).isoformat().replace("+00:00", "Z")

    first = ContextCenter(base_dir=tmp_path)
    first.append_pending_buffer_event("sess-9", {"timestamp": stable_ts, "role": "user", "message": "stable"})
    first.append_pending_buffer_event("sess-9", {"timestamp": waiting_ts, "role": "system", "message": "waiting"})

    second = ContextCenter(base_dir=tmp_path)

    assert second.startup_recovery_result["recovered_sessions"] >= 1
    assert [item.message for item in second.read_detail_events("sess-9")][-1:] == ["stable"]
    assert [item["message"] for item in second.read_pending_buffer_events("sess-9")] == ["waiting"]


def test_durable_context_buffer_replace_pending_events_is_session_local(tmp_path) -> None:
    buffer = DurableContextBuffer.from_base_dir(tmp_path, max_events_per_session=5)
    buffer.append_pending_event(session_id="sess-a", event={"timestamp": "1", "role": "user", "message": "a1"})
    buffer.append_pending_event(session_id="sess-b", event={"timestamp": "1", "role": "user", "message": "b1"})

    buffer.replace_pending_events(session_id="sess-a", events=[{"timestamp": "2", "role": "system", "message": "a2"}])

    assert [item["message"] for item in buffer.read_pending_events(session_id="sess-a")] == ["a2"]
    assert [item["message"] for item in buffer.read_pending_events(session_id="sess-b")] == ["b1"]


def test_context_summary_worker_replace_keeps_only_latest_formal_summary(tmp_path) -> None:
    worker = ContextSummaryWorker.from_base_dir(tmp_path)
    center = ContextCenter(base_dir=tmp_path)
    center.append_context_record("sess-r", SessionContextRecord(session_id="sess-r", kind="message", role="user", content="draft detail"))

    worker.enqueue_summary_write(session_id="sess-r", summary_text="summary-1", replace=True)
    worker.enqueue_summary_write(session_id="sess-r", summary_text="summary-2", replace=True)

    assert [item.message for item in center.read_summary_events("sess-r")] == ["summary-2"]


def test_context_recovery_manager_reports_zero_when_no_pending_sessions(tmp_path) -> None:
    recovery = ContextRecoveryManager.from_base_dir(tmp_path)
    result = recovery.recover_pending_sessions(
        buffer_dir=build_context_storage_paths(tmp_path).buffer_dir,
        flush_session=lambda session_id, now: {"flushed_count": 0},
    )

    assert result == {"recovered_sessions": 0, "flushed_events": 0}
    assert recovery.ready is True
