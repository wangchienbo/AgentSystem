from __future__ import annotations

from pathlib import Path

from app.models.pending_task import PendingTaskRecord
from app.persistence.runtime_state_store import RuntimeStateStore
from app.services.pending_task_orchestrator import PendingTaskOrchestrator
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
    assert store.get_latest_open_task("u1").status == "ready_to_execute"
