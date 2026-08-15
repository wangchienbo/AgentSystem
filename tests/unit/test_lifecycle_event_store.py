"""LifecycleEventStore JSONL 流式持久化 + lifecycle 内存裁剪的单元测试。

验证方案 C 的三个核心行为：
1. 事件以 JSONL 按天分文件追加（不随总量膨胀成单个大 JSON）
2. 内存 _events 只保留每个 App 最近 DEFAULT_MEMORY_EVENT_LIMIT 条
3. include_history=True 时历史全量走磁盘读取
"""

from datetime import UTC, datetime
from pathlib import Path

from app.models.runtime import LifecycleEvent
from app.persistence.lifecycle_event_store import LifecycleEventStore, DEFAULT_MEMORY_EVENT_LIMIT
from app.system.runtime.lifecycle import AppLifecycleService


def _make_event(app_id: str, event_type: str, *, created_at: datetime | None = None) -> LifecycleEvent:
    return LifecycleEvent(
        app_instance_id=app_id,
        event_type=event_type,  # type: ignore[arg-type]
        from_status="draft",
        to_status="installed",
        reason="test",
        created_at=created_at or datetime.now(UTC),
    )


def test_event_store_append_writes_jsonl_by_day(tmp_path: Path) -> None:
    store = LifecycleEventStore(base_dir=tmp_path)
    app_id = "bp.demo.app"
    for i in range(5):
        store.append_event(app_id, _make_event(app_id, "validate"))

    # 按 App 分目录 + 按天分文件
    app_dir = tmp_path / app_id
    assert app_dir.is_dir()
    day_files = list(app_dir.glob("*.jsonl"))
    assert len(day_files) == 1  # 同一天 → 单文件
    lines = day_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5

    # 跨天 → 分文件
    store.append_event(app_id, _make_event(app_id, "install", created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    assert len(list(app_dir.glob("*.jsonl"))) == 2


def test_event_store_history_read_from_disk(tmp_path: Path) -> None:
    store = LifecycleEventStore(base_dir=tmp_path)
    app_id = "bp.demo.hist"
    for i in range(3):
        store.append_event(app_id, _make_event(app_id, "start"))

    # 不带 include_history：读最近
    events = store.list_events(app_id, limit=2)
    assert len(events) == 2

    # include_history=True：全量（正序）
    all_events = store.list_events(app_id, include_history=True)
    assert len(all_events) == 3
    assert isinstance(all_events[0], dict)


def test_lifecycle_memory_events_trimmed_to_limit(tmp_path: Path) -> None:
    store = LifecycleEventStore(base_dir=tmp_path)
    service = AppLifecycleService(event_store=store)
    # 直接操作内部 _events 模拟大量事件（不经过完整 transition 状态机）
    app_id = "bp.demo.trim"
    for i in range(DEFAULT_MEMORY_EVENT_LIMIT + 20):
        service._record_event(app_id, _make_event(app_id, "validate"))

    assert len(service._events[app_id]) == DEFAULT_MEMORY_EVENT_LIMIT
    # 内存只留最近 N 条，但磁盘保留了全部
    disk_events = store.list_events(app_id, include_history=True)
    assert len(disk_events) == DEFAULT_MEMORY_EVENT_LIMIT + 20


def test_lifecycle_load_recovers_recent_from_jsonl(tmp_path: Path) -> None:
    store = LifecycleEventStore(base_dir=tmp_path)
    app_id = "bp.demo.recover"
    for i in range(DEFAULT_MEMORY_EVENT_LIMIT + 10):
        store.append_event(app_id, _make_event(app_id, "stop"))

    # 新实例从 JSONL 恢复最近 N 条
    service = AppLifecycleService(event_store=store)
    assert len(service._events[app_id]) == DEFAULT_MEMORY_EVENT_LIMIT
