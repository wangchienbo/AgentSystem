from __future__ import annotations

from app.services.context_center import ContextCenter
from app.services.context_query_service import ContextQueryService
from app.services.context_recovery_manager import ContextRecoveryManager
from app.services.context_storage_paths import build_context_storage_paths
from app.services.context_summary_worker import ContextSummaryWorker
from app.services.context_writer import ContextWriter


def test_context_center_constructs_formal_service_area(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)

    assert center._writer.paths.base_dir == tmp_path
    assert center._query_service.paths.base_dir == tmp_path
    assert center._recovery_manager.paths.base_dir == tmp_path
    assert center._summary_worker.paths.base_dir == tmp_path
    assert center._recovery_manager.ready is True


def test_context_service_constructors_share_storage_layout(tmp_path) -> None:
    paths = build_context_storage_paths(tmp_path)
    writer = ContextWriter.from_base_dir(tmp_path)
    query = ContextQueryService.from_base_dir(tmp_path)
    recovery = ContextRecoveryManager.from_base_dir(tmp_path)
    summary_worker = ContextSummaryWorker.from_base_dir(tmp_path)

    assert writer.paths == paths
    assert query.paths == paths
    assert recovery.paths == paths
    assert summary_worker.paths == paths
    assert writer.paths.detail_dir.exists()
    assert writer.paths.summary_dir.exists()
    assert writer.paths.buffer_dir.exists()


def test_context_recovery_manager_tracks_ready_state(tmp_path) -> None:
    recovery = ContextRecoveryManager.from_base_dir(tmp_path)

    recovery.mark_recovering()
    assert recovery.recovering is True
    assert recovery.ready is False

    recovery.mark_ready()
    assert recovery.recovering is False
    assert recovery.ready is True


def test_context_recovery_manager_recovers_pending_sessions_before_ready(tmp_path) -> None:
    recovery = ContextRecoveryManager.from_base_dir(tmp_path)
    buffer_dir = build_context_storage_paths(tmp_path).buffer_dir
    buffer_dir.mkdir(parents=True, exist_ok=True)
    (buffer_dir / "sess-a.json").write_text('{"session_id":"sess-a","events":[{"timestamp":"2026-05-04T17:00:00Z"}]}', encoding="utf-8")
    (buffer_dir / "sess-b.json").write_text('{"session_id":"sess-b","events":[{"timestamp":"2026-05-04T17:01:00Z"}]}', encoding="utf-8")

    calls: list[str] = []

    result = recovery.recover_pending_sessions(
        buffer_dir=buffer_dir,
        flush_session=lambda session_id, now: calls.append(session_id) or {"flushed_count": 1},
    )

    assert calls == ["sess-a", "sess-b"]
    assert result == {"recovered_sessions": 2, "flushed_events": 2}
    assert recovery.ready is True
    assert recovery.recovering is False
