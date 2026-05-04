from __future__ import annotations

from app.models.pending_task import (
    PENDING_TASK_ACTION_APPLY_DRAFT_APP,
    PendingTaskRecord,
    STAGE_STATUS_BLOCKED,
    STAGE_STATUS_COMPLETED,
    STAGE_STATUS_IN_PROGRESS,
    WORKFLOW_STAGE_BLOCKED,
    WORKFLOW_STAGE_DONE,
    WORKFLOW_STAGE_IMPLEMENTATION_PENDING,
    WORKFLOW_STAGE_IMPLEMENTATION_RUNNING,
)
from app.services.pending_task_store import PendingTaskStore
from app.services.high_value_fact_messages import acceptance_result_message


def _workflow_hook_message(event: str, stage: str, action: str = "") -> str:
    suffix = f" action={action}" if action else ""
    return f"workflow_hook event={event} stage={stage}{suffix}"


class PendingTaskOrchestrator:
    """Workflow stage transition engine, preserving current draft bootstrap behavior."""

    def __init__(
        self,
        pending_task_store: PendingTaskStore | None = None,
        draft_app_service=None,
        app_application_service=None,
        context_center=None,
    ) -> None:
        self._pending_task_store = pending_task_store
        self._draft_app_service = draft_app_service
        self._app_application_service = app_application_service
        self._context_center = context_center

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

    def _base_stage_update(self, *, stage: str, stage_status: str) -> dict[str, str]:
        return {"current_stage": stage, "stage_status": stage_status}

    def transition_stage(
        self,
        pending_task: PendingTaskRecord,
        *,
        stage: str,
        stage_status: str,
        status: str | None = None,
        next_action: dict[str, object] | None = None,
        known_fact_updates: dict[str, object] | None = None,
        artifact: dict[str, object] | None = None,
    ) -> PendingTaskRecord:
        updates: dict[str, object] = {
            **self._base_stage_update(stage=stage, stage_status=stage_status),
        }
        if status is not None:
            updates["status"] = status
        if next_action is not None:
            updates["next_recommended_action"] = next_action
        if known_fact_updates:
            updates["known_facts"] = {**pending_task.known_facts, **known_fact_updates}
        if artifact is not None:
            updates["artifacts"] = [*pending_task.artifacts, artifact]
        updated = pending_task.model_copy(update=updates)
        if self._pending_task_store is not None:
            self._pending_task_store.upsert_task(updated)
        self._emit_workflow_hook(
            pending_task,
            event=(
                "stage_blocked" if stage_status == STAGE_STATUS_BLOCKED else
                "stage_completed" if stage_status == STAGE_STATUS_COMPLETED else
                "stage_entered" if stage_status == STAGE_STATUS_IN_PROGRESS else
                "stage_updated"
            ),
            stage=stage,
            action=(next_action or {}).get("type", "") if next_action else "",
        )
        return updated

    def mark_stage_in_progress(
        self,
        pending_task: PendingTaskRecord,
        *,
        stage: str,
        next_action: dict[str, object] | None = None,
    ) -> PendingTaskRecord:
        return self.transition_stage(
            pending_task,
            stage=stage,
            stage_status=STAGE_STATUS_IN_PROGRESS,
            next_action=next_action,
        )

    def mark_stage_completed(
        self,
        pending_task: PendingTaskRecord,
        *,
        stage: str,
        next_stage: str | None = None,
        status: str | None = None,
        next_action: dict[str, object] | None = None,
        artifact: dict[str, object] | None = None,
    ) -> PendingTaskRecord:
        target_stage = next_stage or stage
        return self.transition_stage(
            pending_task,
            stage=target_stage,
            stage_status=STAGE_STATUS_COMPLETED,
            status=status,
            next_action=next_action,
            artifact=artifact,
        )

    def mark_blocked(
        self,
        pending_task: PendingTaskRecord,
        *,
        reason: str,
        next_action: dict[str, object] | None = None,
    ) -> PendingTaskRecord:
        return self.transition_stage(
            pending_task,
            stage=WORKFLOW_STAGE_BLOCKED,
            stage_status=STAGE_STATUS_BLOCKED,
            status="blocked",
            next_action=next_action,
            known_fact_updates={"blocked_reason": reason},
        )

    def capture_repo_context(
        self,
        pending_task: PendingTaskRecord,
        *,
        active_repo_path: str,
        primary_readme_path: str,
        key_docs: list[str] | None = None,
        target_modules: list[str] | None = None,
    ) -> PendingTaskRecord:
        repo_context = {
            "active_repo_path": active_repo_path,
            "primary_readme_path": primary_readme_path,
            "key_docs": list(key_docs or []),
            "target_modules": list(target_modules or []),
        }
        updated = pending_task.model_copy(update={"repo_context": repo_context})
        if self._pending_task_store is not None:
            self._pending_task_store.upsert_task(updated)
        return updated

    def capture_upgrade_plan(
        self,
        pending_task: PendingTaskRecord,
        *,
        build_install_plan: list[str] | None = None,
        activation_reload_path: list[str] | None = None,
        rollback_hint: str = "",
    ) -> PendingTaskRecord:
        upgrade_plan = {
            "build_install_plan": list(build_install_plan or []),
            "activation_reload_path": list(activation_reload_path or []),
            "rollback_hint": rollback_hint,
        }
        updated = pending_task.model_copy(update={"upgrade_plan": upgrade_plan})
        if self._pending_task_store is not None:
            self._pending_task_store.upsert_task(updated)
        return updated

    def capture_acceptance_plan(
        self,
        pending_task: PendingTaskRecord,
        *,
        test_probe_commands: list[str] | None = None,
        http_runtime_verification_points: list[str] | None = None,
        success_criteria: list[str] | None = None,
    ) -> PendingTaskRecord:
        acceptance_plan = {
            "test_probe_commands": list(test_probe_commands or []),
            "http_runtime_verification_points": list(http_runtime_verification_points or []),
            "success_criteria": list(success_criteria or []),
            "results": list((pending_task.acceptance_plan or {}).get("results") or []),
        }
        updated = pending_task.model_copy(update={"acceptance_plan": acceptance_plan})
        if self._pending_task_store is not None:
            self._pending_task_store.upsert_task(updated)
        self._emit_workflow_hook(pending_task, event="acceptance_started", stage=pending_task.current_stage)
        return updated

    def capture_acceptance_result(
        self,
        pending_task: PendingTaskRecord,
        *,
        status: str,
        summary: str,
        evidence: dict[str, object] | None = None,
    ) -> PendingTaskRecord:
        acceptance_plan = {
            **pending_task.acceptance_plan,
            "results": [
                *(pending_task.acceptance_plan.get("results") or []),
                {"status": status, "summary": summary, "evidence": dict(evidence or {})},
            ],
        }
        updated = pending_task.model_copy(update={"acceptance_plan": acceptance_plan})
        if self._pending_task_store is not None:
            self._pending_task_store.upsert_task(updated)
        if self._context_center is not None and pending_task.session_id:
            from app.models.context import SessionContextRecord
            self._context_center.append_context(
                SessionContextRecord(
                    session_id=pending_task.session_id,
                    kind="system_note",
                    role="system",
                    content=acceptance_result_message(status=status, summary=summary),
                    metadata={"acceptance": True, **dict(evidence or {})},
                )
            )
        self._emit_workflow_hook(pending_task, event="acceptance_completed", stage=pending_task.current_stage)
        return updated

    def _emit_workflow_hook(self, pending_task: PendingTaskRecord, *, event: str, stage: str, action: str = "") -> None:
        if self._context_center is None or not pending_task.session_id:
            return
        from app.models.context import SessionContextRecord
        self._context_center.append_context(
            SessionContextRecord(
                session_id=pending_task.session_id,
                kind="system_note",
                role="system",
                content=_workflow_hook_message(event=event, stage=stage, action=action),
                metadata={"workflow_hook": True, "event": event, "stage": stage, **({"action": action} if action else {})},
            )
        )

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
            **self._base_stage_update(
                stage=WORKFLOW_STAGE_IMPLEMENTATION_PENDING if not missing_fields else pending_task.current_stage,
                stage_status=STAGE_STATUS_COMPLETED if not missing_fields else pending_task.stage_status,
            ),
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
            **self._base_stage_update(stage=WORKFLOW_STAGE_IMPLEMENTATION_RUNNING, stage_status=STAGE_STATUS_COMPLETED),
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
            "next_recommended_action": {
                "type": PENDING_TASK_ACTION_APPLY_DRAFT_APP,
                "app_id": app_id,
                "handoff_target": "AppApplicationService",
            },
            **self._base_stage_update(stage=WORKFLOW_STAGE_DONE, stage_status=STAGE_STATUS_COMPLETED),
        })
        self._pending_task_store.upsert_task(updated)
        return updated
