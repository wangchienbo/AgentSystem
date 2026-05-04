from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.context_center import ContextCenter
from app.services.context_reorder_window import SessionLocalReorderWindow


def test_session_local_reorder_window_sorts_out_of_order_events() -> None:
    window = SessionLocalReorderWindow()
    now = datetime(2026, 5, 4, 17, 10, tzinfo=UTC)
    events = [
        {"timestamp": "2026-05-04T17:04:00Z", "role": "user", "message": "later"},
        {"timestamp": "2026-05-04T17:02:00Z", "role": "user", "message": "earlier"},
    ]

    result = window.rebalance(events, now=now)

    assert [item["message"] for item in result.stable_events] == ["earlier", "later"]
    assert result.waiting_events == []


def test_session_local_reorder_window_keeps_recent_events_waiting() -> None:
    window = SessionLocalReorderWindow()
    now = datetime(2026, 5, 4, 17, 10, tzinfo=UTC)
    events = [
        {"timestamp": "2026-05-04T17:08:30Z", "role": "user", "message": "recent-1"},
        {"timestamp": "2026-05-04T17:09:30Z", "role": "system", "message": "recent-2"},
    ]

    result = window.rebalance(events, now=now)

    assert result.stable_events == []
    assert [item["message"] for item in result.waiting_events] == ["recent-1", "recent-2"]


def test_context_center_flushes_stable_pending_events_and_keeps_waiting(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path)
    center.append_pending_buffer_event("sess-1", {"timestamp": "2099-05-04T17:02:00Z", "role": "user", "message": "stable"})
    center.append_pending_buffer_event("sess-1", {"timestamp": "2099-05-04T17:08:30Z", "role": "system", "message": "waiting"})

    result = center.flush_stable_pending_events("sess-1", now=datetime(2099, 5, 4, 17, 10, tzinfo=UTC))
    detail_events = center.read_detail_events("sess-1")
    pending_events = center.read_pending_buffer_events("sess-1")
    summaries = center.read_summary_events("sess-1")

    assert result["flushed_count"] == 1
    assert result["waiting_count"] == 1
    assert [item.message for item in detail_events][-1:] == ["stable"]
    assert [item["message"] for item in pending_events] == ["waiting"]
    assert [item.message for item in summaries][-1:] == ["[user] stable"]


def test_context_center_recovers_pending_buffer_on_startup(tmp_path) -> None:
    base_now = datetime.now(UTC)
    stable_ts = (base_now.replace(microsecond=0) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    waiting_ts = (base_now.replace(microsecond=0) - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")

    first = ContextCenter(base_dir=tmp_path)
    first.append_pending_buffer_event("sess-1", {"timestamp": stable_ts, "role": "user", "message": "stable"})
    first.append_pending_buffer_event("sess-1", {"timestamp": waiting_ts, "role": "system", "message": "waiting"})

    second = ContextCenter(base_dir=tmp_path)

    assert second.startup_recovery_result["recovered_sessions"] >= 1
    assert [item.message for item in second.read_detail_events("sess-1")][-1:] == ["stable"]
    assert [item["message"] for item in second.read_pending_buffer_events("sess-1")] == ["waiting"]
