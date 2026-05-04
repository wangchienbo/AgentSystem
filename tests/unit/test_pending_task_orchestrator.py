from __future__ import annotations

from pathlib import Path

from app.models.pending_task import (
    PENDING_TASK_ACTION_APPLY_DRAFT_APP,
    PendingTaskRecord,
    STAGE_STATUS_PENDING,
    STAGE_STATUS_VALUES,
    WORKFLOW_STAGE_INTENT_RECEIVED,
    WORKFLOW_STAGE_VALUES,
)
from app.persistence.runtime_state_store import RuntimeStateStore
from app.services.app_application_service import AppApplicationService
from app.services.draft_app_application_service import DraftAppApplicationService
from app.services.draft_app_service import DraftAppService
from app.services.pending_task_orchestrator import PendingTaskOrchestrator
from app.system.runtime.lifecycle import AppLifecycleService
from app.system.runtime.runtime_host import AppRuntimeHostService
from app.system.runtime.pending_task_store import PendingTaskStore


def test_pending_task_orchestrator_advances_default_runtime_profile(tmp_path: Path):
    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    task = PendingTaskRecord(
        task_id="pt-1",
        user_id="u1",
        intent="create_app",
        status="drafted",
        current_stage="solution_drafting",
        stage_status="in_progress",
        missing_fields=["runtime_profile", "execution_mode"],
        next_recommended_action={"type": "continue_draft_app_setup"},
    )
    store.upsert_task(task)
    orchestrator = PendingTaskOrchestrator(store)

    updated = orchestrator.advance_if_possible(task)

    assert updated is not None
    assert updated.known_facts["runtime_profile"] == "default"
    assert updated.known_facts["execution_mode"] == "service"
    assert updated.status == "ready_to_execute"
    assert updated.current_stage == "implementation_pending"
    assert updated.stage_status == "completed"
    assert updated.missing_fields == []
    assert updated.next_recommended_action["type"] == "execute_draft_app_setup"
    assert store.get_latest_open_task("u1").status == "ready_to_execute"


def test_pending_task_orchestrator_executes_ready_draft_setup(tmp_path: Path):
    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    task = PendingTaskRecord(
        task_id="pt-2",
        user_id="u1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="implementation_pending",
        stage_status="completed",
        known_facts={"runtime_profile": "default", "execution_mode": "service"},
        missing_fields=[],
        next_recommended_action={"type": "execute_draft_app_setup"},
    )
    store.upsert_task(task)
    orchestrator = PendingTaskOrchestrator(store)

    updated = orchestrator.advance_if_possible(task)

    assert updated is not None
    assert updated.known_facts["draft_setup_prepared"] is True
    assert updated.current_stage == "implementation_running"
    assert updated.stage_status == "completed"
    assert updated.next_recommended_action["type"] == "report_draft_ready"


def test_pending_task_orchestrator_reports_ready_completion(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    store = PendingTaskStore(runtime_store)
    draft_service = DraftAppService(runtime_store)
    draft_app = draft_service.create_draft_app(owner_user_id="u1", name="测试 app", goal="创建一个 app")
    task = PendingTaskRecord(
        task_id="pt-3",
        user_id="u1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="implementation_running",
        stage_status="completed",
        known_facts={
            "runtime_profile": "default",
            "execution_mode": "service",
            "draft_setup_prepared": True,
        },
        missing_fields=[],
        target_ref={"app_id": draft_app.id, "target_id": draft_app.id},
        next_recommended_action={"type": "report_draft_ready"},
    )
    store.upsert_task(task)
    orchestrator = PendingTaskOrchestrator(store, draft_service)

    updated = orchestrator.advance_if_possible(task)

    assert updated is not None
    assert updated.status == "completed"
    assert updated.current_stage == "done"
    assert updated.stage_status == "completed"
    assert updated.known_facts["draft_ready_reported"] is True
    assert updated.known_facts["lifecycle_ready_status"] == "compiled"
    assert updated.next_recommended_action["type"] == "apply_draft_app"
    assert updated.next_recommended_action["app_id"] == draft_app.id
    assert updated.next_recommended_action["handoff_target"] == "AppApplicationService"
    assert draft_service.get_app(draft_app.id).status == "compiled"


def test_pending_task_record_supports_wave1_workflow_fields():
    task = PendingTaskRecord(task_id="pt-x", user_id="u1", intent="create_app")

    assert task.workflow_type == "draft_app_bootstrap"
    assert task.current_stage == WORKFLOW_STAGE_INTENT_RECEIVED
    assert task.stage_status == STAGE_STATUS_PENDING
    assert task.solution_draft == {}
    assert task.review_result == {}
    assert task.task_list == []
    assert task.repo_context == {}
    assert task.implementation_plan == {}
    assert task.upgrade_plan == {}
    assert task.acceptance_plan == {}
    assert task.artifacts == []


def test_pending_task_workflow_constants_are_stable() -> None:
    assert WORKFLOW_STAGE_INTENT_RECEIVED in WORKFLOW_STAGE_VALUES
    assert "implementation_running" in WORKFLOW_STAGE_VALUES
    assert "done" in WORKFLOW_STAGE_VALUES
    assert STAGE_STATUS_PENDING in STAGE_STATUS_VALUES
    assert "completed" in STAGE_STATUS_VALUES


def test_pending_task_orchestrator_supports_generic_stage_transition_helpers(tmp_path: Path):
    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    task = PendingTaskRecord(
        task_id="pt-generic-1",
        user_id="u1",
        intent="ship change",
        current_stage="solution_reviewing",
        stage_status="pending",
        next_recommended_action={"type": "approve_solution_draft"},
    )
    store.upsert_task(task)
    orchestrator = PendingTaskOrchestrator(store)

    in_progress = orchestrator.mark_stage_in_progress(
        task,
        stage="tasklist_preparing",
        next_action={"type": "materialize_task_list"},
    )
    completed = orchestrator.mark_stage_completed(
        in_progress,
        stage="tasklist_preparing",
        next_stage="repo_locating",
        status="ready_to_execute",
        next_action={"type": "locate_repo_context"},
        artifact={"kind": "task_list", "id": "tl-1"},
    )

    assert in_progress.current_stage == "tasklist_preparing"
    assert in_progress.stage_status == "in_progress"
    assert in_progress.next_recommended_action["type"] == "materialize_task_list"
    assert completed.current_stage == "repo_locating"
    assert completed.stage_status == "completed"
    assert completed.status == "ready_to_execute"
    assert completed.next_recommended_action["type"] == "locate_repo_context"
    assert completed.artifacts[-1]["kind"] == "task_list"


def test_pending_task_orchestrator_can_mark_blocked_state(tmp_path: Path):
    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    task = PendingTaskRecord(
        task_id="pt-blocked-1",
        user_id="u1",
        intent="ship change",
        current_stage="repo_locating",
        stage_status="in_progress",
    )
    store.upsert_task(task)
    orchestrator = PendingTaskOrchestrator(store)

    blocked = orchestrator.mark_blocked(
        task,
        reason="repo path missing",
        next_action={"type": "locate_repo_context"},
    )

    assert blocked.current_stage == "blocked"
    assert blocked.stage_status == "blocked"
    assert blocked.status == "blocked"
    assert blocked.known_facts["blocked_reason"] == "repo path missing"
    assert blocked.next_recommended_action["type"] == "locate_repo_context"


    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    lifecycle = AppLifecycleService(runtime_store)
    runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=runtime_store)
    draft_app = draft_service.create_draft_app(owner_user_id="u1", name="测试 app", goal="创建一个 app")
    draft_service.mark_ready_for_lifecycle(draft_app.id)
    application = AppApplicationService(
        draft_app_application_service=DraftAppApplicationService(draft_service, lifecycle, runtime_host)
    )

    from app.models.chat import InterpretedCommand
    import asyncio

    response = asyncio.run(
        application.handle(
            InterpretedCommand(
                intent="apply_draft_app",
                raw_input="apply_draft_app",
                target_app=draft_app.id,
                parameters={"app_id": draft_app.id},
            ),
            session_id="s1",
            available_apps=[],
        )
    )

    assert response is not None
    assert response.type == "progress"
    assert response.related_app == draft_app.id
    assert lifecycle.get_instance(draft_app.id).status == "running"
    assert response.data["lifecycle_transition"] == "draft_to_running_activation"
    assert response.actions[0].payload["intent"] == "query_app"
