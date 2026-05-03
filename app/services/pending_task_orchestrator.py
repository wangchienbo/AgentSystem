from __future__ import annotations

from app.models.pending_task import PendingTaskRecord
from app.services.pending_task_store import PendingTaskStore


class PendingTaskOrchestrator:
    """Thin orchestration layer for bootstrap pending-task continuation logic."""

    def __init__(self, pending_task_store: PendingTaskStore | None = None, draft_app_service=None) -> None:
        self._pending_task_store = pending_task_store
        self._draft_app_service = draft_app_service

    def advance_if_possible(self, pending_task: PendingTaskRecord | None) -> PendingTaskRecord | None:
        if pending_task is None or self._pending_task_store is None:
            return pending_task

        next_action_type = (pending_task.next_recommended_action or {}).get("type", "")
        if next_action_type == "continue_draft_app_setup":
            return self._continue_draft_app_setup(pending_task)
        if next_action_type == "execute_draft_app_setup":
            return self._execute_draft_app_setup(pending_task)
        if next_action_type == "report_draft_ready":
            return self._report_draft_ready(pending_task)
        return pending_task

    def _continue_draft_app_setup(self, pending_task: PendingTaskRecord) -> PendingTaskRecord:
        missing_fields = list(pending_task.missing_fields)
        known_facts = dict(pending_task.known_facts)
        changed = False

        if "runtime_profile" in missing_fields and "runtime_profile" not in known_facts:
            known_facts["runtime_profile"] = "default"
            missing_fields.remove("runtime_profile")
            changed = True

        if "execution_mode" in missing_fields and "execution_mode" not in known_facts:
            known_facts["execution_mode"] = "service"
            missing_fields.remove("execution_mode")
            changed = True

        if not changed and not missing_fields and pending_task.status != "ready_to_execute":
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

    def _execute_draft_app_setup(self, pending_task: PendingTaskRecord) -> PendingTaskRecord:
        if pending_task.missing_fields:
            return pending_task
        known_facts = dict(pending_task.known_facts)
        if known_facts.get("draft_setup_prepared") is True and (pending_task.next_recommended_action or {}).get("type") == "report_draft_ready":
            return pending_task
        known_facts["draft_setup_prepared"] = True
        updated = pending_task.model_copy(update={
            "known_facts": known_facts,
            "status": "ready_to_execute",
            "next_recommended_action": {"type": "report_draft_ready"},
        })
        self._pending_task_store.upsert_task(updated)
        return updated

    def _report_draft_ready(self, pending_task: PendingTaskRecord) -> PendingTaskRecord:
        known_facts = dict(pending_task.known_facts)
        if known_facts.get("draft_ready_reported") is True:
            return pending_task
        known_facts["draft_ready_reported"] = True
        app_id = pending_task.target_ref.get("app_id") or pending_task.target_ref.get("target_id")
        if self._draft_app_service is not None and app_id:
            try:
                self._draft_app_service.mark_ready_for_lifecycle(app_id)
                known_facts["lifecycle_ready_status"] = "compiled"
            except Exception:
                pass
        updated = pending_task.model_copy(update={
            "known_facts": known_facts,
            "status": "completed",
            "next_recommended_action": {"type": "draft_ready_reported"},
        })
        self._pending_task_store.upsert_task(updated)
        return updated
