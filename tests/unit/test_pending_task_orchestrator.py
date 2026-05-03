from __future__ import annotations

from pathlib import Path

from app.models.pending_task import PendingTaskRecord
from app.persistence.runtime_state_store import RuntimeStateStore
from app.services.app_application_service import AppApplicationService
from app.services.draft_app_application_service import DraftAppApplicationService
from app.services.draft_app_service import DraftAppService
from app.services.pending_task_orchestrator import PendingTaskOrchestrator
from app.system.runtime.lifecycle import AppLifecycleService
from app.system.runtime.pending_task_store import PendingTaskStore


def test_pending_task_orchestrator_advances_default_runtime_profile(tmp_path: Path):
    store = PendingTaskStore(RuntimeStateStore(base_dir=str(tmp_path / "runtime")))
    task = PendingTaskRecord(
        task_id="pt-1",
        user_id="u1",
        intent="create_app",
        status="drafted",
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
        known_facts={"runtime_profile": "default", "execution_mode": "service"},
        missing_fields=[],
        next_recommended_action={"type": "execute_draft_app_setup"},
    )
    store.upsert_task(task)
    orchestrator = PendingTaskOrchestrator(store)

    updated = orchestrator.advance_if_possible(task)

    assert updated is not None
    assert updated.known_facts["draft_setup_prepared"] is True
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
    assert updated.known_facts["draft_ready_reported"] is True
    assert updated.known_facts["lifecycle_ready_status"] == "compiled"
    assert updated.next_recommended_action["type"] == "apply_draft_app"
    assert updated.next_recommended_action["app_id"] == draft_app.id
    assert updated.next_recommended_action["handoff_target"] == "AppApplicationService"
    assert draft_service.get_app(draft_app.id).status == "compiled"


def test_app_application_service_applies_draft_into_lifecycle(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    lifecycle = AppLifecycleService(runtime_store)
    draft_app = draft_service.create_draft_app(owner_user_id="u1", name="测试 app", goal="创建一个 app")
    draft_service.mark_ready_for_lifecycle(draft_app.id)
    application = AppApplicationService(
        draft_app_application_service=DraftAppApplicationService(draft_service, lifecycle)
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
    assert lifecycle.get_instance(draft_app.id).status == "compiled"
