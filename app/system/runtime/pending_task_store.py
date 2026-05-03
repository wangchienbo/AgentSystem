from __future__ import annotations

from datetime import UTC, datetime

from app.models.pending_task import PendingTaskRecord
from app.persistence.runtime_state_store import RuntimeStateStore


class PendingTaskStore:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._store = store or RuntimeStateStore()
        self._tasks_by_user: dict[str, list[PendingTaskRecord]] = {}
        self._load()

    def list_open_tasks(self, user_id: str) -> list[PendingTaskRecord]:
        return [
            task for task in self._tasks_by_user.get(user_id, [])
            if task.status not in {"completed", "abandoned"}
        ]

    def get_latest_open_task(self, user_id: str) -> PendingTaskRecord | None:
        open_tasks = self.list_open_tasks(user_id)
        if not open_tasks:
            return None
        return max(open_tasks, key=lambda item: item.updated_at)

    def upsert_task(self, task: PendingTaskRecord) -> PendingTaskRecord:
        task.updated_at = datetime.now(UTC)
        items = self._tasks_by_user.setdefault(task.user_id, [])
        for idx, existing in enumerate(items):
            if existing.task_id == task.task_id:
                items[idx] = task
                self._save()
                return task
        items.append(task)
        self._save()
        return task

    def mark_completed(self, task_id: str, user_id: str) -> PendingTaskRecord | None:
        return self._update_status(task_id, user_id, "completed")

    def mark_abandoned(self, task_id: str, user_id: str) -> PendingTaskRecord | None:
        return self._update_status(task_id, user_id, "abandoned")

    def _update_status(self, task_id: str, user_id: str, status: str) -> PendingTaskRecord | None:
        items = self._tasks_by_user.get(user_id, [])
        for idx, existing in enumerate(items):
            if existing.task_id == task_id:
                updated = existing.model_copy(update={"status": status, "updated_at": datetime.now(UTC)})
                items[idx] = updated
                self._save()
                return updated
        return None

    def _save(self) -> None:
        self._store.save_nested_mapping("pending_tasks", self._tasks_by_user)

    def _load(self) -> None:
        raw = self._store.load_json("pending_tasks", {})
        tasks_by_user: dict[str, list[PendingTaskRecord]] = {}
        if not isinstance(raw, dict):
            self._tasks_by_user = {}
            return
        for user_id, items in raw.items():
            if not isinstance(items, list):
                continue
            tasks_by_user[user_id] = [PendingTaskRecord.model_validate(item) for item in items]
        self._tasks_by_user = tasks_by_user
