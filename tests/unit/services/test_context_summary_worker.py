from __future__ import annotations

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


def test_context_summary_worker_respects_single_active_job(tmp_path) -> None:
    worker = ContextSummaryWorker.from_base_dir(tmp_path)
    worker.active_jobs = 1
    worker.queued_jobs.append({"session_id": "sess-1", "summary_text": "summary-1", "role": "system"})

    result = worker.drain_once()

    assert result == {"processed": 0, "queued": 1, "active": 1}
    assert len(worker.queued_jobs) == 1


def test_context_center_exposes_summary_write_path(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)

    result = center.enqueue_summary_write("sess-2", "summary-2", role="system")
    summaries = center.read_summary_events("sess-2")

    assert result["processed"] == 1
    assert [item.message for item in summaries] == ["summary-2"]
