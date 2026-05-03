from __future__ import annotations

from app.models.pending_task import PendingTaskRecord
from app.services.pending_task_store import PendingTaskStore


class PendingTaskOrchestrator:
    """Thin orchestration layer for bootstrap pending-task continuation logic."""

    def __init__(self, pending_task_store: PendingTaskStore | None = None) -> None:
        self._pending_task_store = pending_task_store

    def advance_if_possible(self, pending_task: PendingTaskRecord | None) -> PendingTaskRecord | None:
        if pending_task is None or self._pending_task_store is None:
            return pending_task
        missing_fields = list(pending_task.missing_fields)
        known_facts = dict(pending_task.known_facts)
        changed = False

        if "runtime_profile" in missing_fields and "runtime_profile" not in known_facts:
            known_facts["runtime_profile"] = "default"
            missing_fields.remove("runtime_profile")
            changed = True

        if not changed:
            return pending_task

        new_status = "ready_to_execute" if not missing_fields else pending_task.status
        next_action = {"type": "execute_draft_app_setup"} if not missing_fields else pending_task.next_recommended_action
        updated = pending_task.model_copy(update={
            "known_facts": known_facts,
            "missing_fields": missing_fields,
            "status": new_status,
            "next_recommended_action": next_action,
        })
        self._pending_task_store.upsert_task(updated)
        return updated
