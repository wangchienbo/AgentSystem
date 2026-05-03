from __future__ import annotations

from pathlib import Path

from app.models.pending_task import PendingTaskRecord
from app.persistence.runtime_state_store import RuntimeStateStore
from app.system.runtime.pending_task_store import PendingTaskStore


def test_pending_task_store_returns_latest_open_task(tmp_path: Path):
    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    old_task = PendingTaskRecord(
        task_id="pt-old",
        user_id="u1",
        intent="create_app",
        status="pending_input",
        draft_payload={"name": "draft-one"},
    )
    new_task = PendingTaskRecord(
        task_id="pt-new",
        user_id="u1",
        intent="modify_app",
        status="ready_to_execute",
        draft_payload={"name": "draft-two"},
    )
    store.upsert_task(old_task)
    store.upsert_task(new_task)

    latest = store.get_latest_open_task("u1")

    assert latest is not None
    assert latest.task_id == "pt-new"
    assert len(store.list_open_tasks("u1")) == 2


def test_pending_task_store_persists_and_filters_completed(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    store = PendingTaskStore(RuntimeStateStore(base_dir=str(runtime_dir)))
    task = PendingTaskRecord(
        task_id="pt-1",
        user_id="u2",
        intent="create_app",
        status="pending_input",
    )
    store.upsert_task(task)
    store.mark_completed("pt-1", "u2")

    reloaded = PendingTaskStore(RuntimeStateStore(base_dir=str(runtime_dir)))

    assert reloaded.get_latest_open_task("u2") is None
    assert reloaded.list_open_tasks("u2") == []
