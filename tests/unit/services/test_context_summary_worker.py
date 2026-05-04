from __future__ import annotations

from app.models.context import SessionContextRecord
from app.services.context_center import ContextCenter
from app.services.context_summary_worker import ContextSummaryWorker


def test_context_summary_worker_writes_summary_through_single_thread_queue(tmp_path) -> None:
    worker = ContextSummaryWorker.from_base_dir(tmp_path)

    result = worker.enqueue_summary_write(session_id="sess-1", summary_text="summary-1")

    center = ContextCenter(base_dir=tmp_path)
    summaries = center.read_summary_events("sess-1")

    assert worker.max_concurrency == 1
    assert result["processed"] == 1
    assert result["queued"] == 0
    assert [item.message for item in summaries] == ["summary-1"]


def test_context_summary_worker_replaces_previous_formal_summary(tmp_path) -> None:
    worker = ContextSummaryWorker.from_base_dir(tmp_path)
    worker.enqueue_summary_write(session_id="sess-1", summary_text="summary-1", replace=True)
    worker.enqueue_summary_write(session_id="sess-1", summary_text="summary-2", replace=True)

    center = ContextCenter(base_dir=tmp_path)
    summaries = center.read_summary_events("sess-1")

    assert [item.message for item in summaries] == ["summary-2"]


def test_context_summary_worker_respects_single_active_job(tmp_path) -> None:
    worker = ContextSummaryWorker.from_base_dir(tmp_path)
    worker.active_jobs = 1
    worker.queued_jobs.append({"session_id": "sess-1", "summary_text": "summary-1", "role": "system"})

    result = worker.drain_once()

    assert result == {"processed": 0, "queued": 1, "active": 1}
    assert len(worker.queued_jobs) == 1


def test_context_summary_worker_failure_does_not_block_existing_provisional_summary(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)
    center.append_context_record("sess-5", SessionContextRecord(session_id="sess-5", kind="message", role="user", content="draft detail"))

    worker = ContextSummaryWorker.from_base_dir(tmp_path)
    result = worker.enqueue_summary_write(session_id="sess-5", summary_text="FAIL: llm unavailable", replace=True)
    summaries = center.read_summary_events("sess-5")

    assert result["processed"] == 0
    assert result["failed"] == 1
    assert [item.message for item in summaries] == ["[user] draft detail"]


def test_context_center_exposes_summary_write_path(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)

    result = center.enqueue_summary_write("sess-2", "summary-2", role="system", replace=True)
    summaries = center.read_summary_events("sess-2")

    assert result["processed"] == 1
    assert [item.message for item in summaries] == ["summary-2"]


def test_context_center_recent_working_memory_view_merges_stable_and_pending(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)
    center.append_context_record("sess-3", SessionContextRecord(session_id="sess-3", kind="message", role="user", content="stable-1"))
    center.append_context_record("sess-3", SessionContextRecord(session_id="sess-3", kind="system_note", role="system", content="stable-2"))
    center.append_pending_buffer_event("sess-3", {"timestamp": "2099-05-04T18:00:00Z", "role": "assistant", "message": "pending-1"})

    view = center.get_recent_working_memory_view("sess-3", limit=300)

    assert view["session_id"] == "sess-3"
    assert [item["message"] for item in view["stable"]] == ["stable-1", "stable-2"]
    assert [item["message"] for item in view["pending"]] == ["pending-1"]


def test_context_center_writes_provisional_summary_immediately_for_formal_detail(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)
    center.append_context_record("sess-4", SessionContextRecord(session_id="sess-4", kind="message", role="user", content="hello world"))

    summaries = center.read_summary_events("sess-4")

    assert [item.message for item in summaries] == ["[user] hello world"]
