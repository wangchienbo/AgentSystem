from __future__ import annotations

import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from app.models.chat import ChatMessageRequest, TaskContinuationDecision
from app.models.pending_task import PendingTaskRecord
from app.persistence.runtime_state_store import RuntimeStateStore
from app.services.app_application_service import AppApplicationService
from app.services.draft_app_application_service import DraftAppApplicationService
from app.services.draft_app_service import DraftAppService
from app.services.light_brain_memory import LightBrainMemory
from app.system.gateway.light_brain_gateway import LightBrainGateway
from app.system.runtime.lifecycle import AppLifecycleService
from app.system.runtime.runtime_host import AppRuntimeHostService


class _Interpreter:
    def interpret(self, message, available_apps, user_id, session_id):
        from app.models.chat import InterpretedCommand

        return InterpretedCommand(intent="greet", raw_input=message, user_id=user_id)


class _PendingTaskStore:
    def __init__(self, task):
        self.task = task

    def get_latest_open_task(self, user_id):
        return self.task if user_id == "u1" else None

    def upsert_task(self, task):
        self.task = task
        return task


class _RecentWindow:
    def __init__(self):
        self.records = []


class _ContextCenter:
    def __init__(self):
        self.records = []

    def register_session_node(self, node):
        return None

    def get_recent_working_memory_view(self, session_id, limit=300):
        return {"session_id": session_id, "stable": [{"id": f"detail:{session_id}:1", "message": "draft create app pending"}], "pending": [{"message": "recent pending"}]}

    def get_recent_working_memory_summaries(self, session_id, limit=5):
        return [{"id": f"summary:{session_id}:1", "message": "recent summary"}]

    def get_detail_record_by_reference(self, session_id, reference_id):
        return {"id": reference_id, "message": "detail payload"}

    def get_recent_context(self, session_id, limit=100):
        return _RecentWindow()

    def read_linked_context(self, session_id, limit=50):
        return []

    def get_child_sessions(self, session_id):
        return []

    def append_context(self, record):
        self.records.append(record)


def test_gateway_appends_pending_task_note_to_context():
    memory = LightBrainMemory()
    context_center = _ContextCenter()
    task = PendingTaskRecord(
        task_id="pt-1",
        user_id="u1",
        intent="create_app",
        status="pending_input",
        target_ref={"target_id": "app_123"},
        missing_fields=["runtime_profile"],
    )
    gateway = LightBrainGateway(
        memory=memory,
        interpreter=_Interpreter(),
        context_center=context_center,
        pending_task_store=_PendingTaskStore(task),
    )

    response = asyncio.run(
        gateway.receive_message(
            ChatMessageRequest(user_id="u1", channel="test", message="继续")
        )
    )

    assert response.content
    note_contents = [record.content for record in context_center.records if record.role == "system"]
    assert any("pending_task task_id=pt-1" in content for content in note_contents)
    assert any("continuation_decision mode=continue_task" in content for content in note_contents)


def test_gateway_can_recover_continue_from_context_center_without_pending_task():
    memory = LightBrainMemory()
    context_center = _ContextCenter()
    gateway = LightBrainGateway(
        memory=memory,
        interpreter=_Interpreter(),
        context_center=context_center,
        pending_task_store=_PendingTaskStore(None),
    )

    response = asyncio.run(
        gateway.receive_message(
            ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="sess-ctx-1")
        )
    )

    assert response.type == "progress"
    assert "Context Center" in response.content
    assert response.data is not None
    assert response.data["context_view"]["stable"][0]["message"] == "draft create app pending"


def test_gateway_builds_draft_create_decision_without_pending_task():
    gateway = LightBrainGateway(memory=LightBrainMemory(), interpreter=_Interpreter())

    decision = gateway._build_continuation_decision("创建一个写代码 app", None)

    assert decision is not None
    assert decision.conversation_mode == "draft_create"
    assert decision.next_action["type"] == "create_draft_app"


def test_gateway_materializes_draft_app_and_pending_task(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
    )

    decision = gateway._build_continuation_decision("创建一个写代码 app", None)
    assert decision is not None
    gateway._materialize_continuation_decision(decision, user_id="u1", session_id="s1", message="创建一个写代码 app")

    assert decision.pending_task_id is not None
    assert decision.target_ref["app_id"].startswith("app_draft_")
    latest_task = pending_store.get_latest_open_task("u1")
    assert latest_task is not None
    assert latest_task.status == "drafted"
    assert latest_task.target_ref["app_id"] == decision.target_ref["app_id"]
    assert draft_service.get_app(decision.target_ref["app_id"]) is not None


def test_gateway_continue_task_returns_progress_response(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    from app.services.pending_task_orchestrator import PendingTaskOrchestrator
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
        pending_task_orchestrator=PendingTaskOrchestrator(pending_store, draft_service),
    )

    create_decision = gateway._build_continuation_decision("创建一个写代码 app", None)
    assert create_decision is not None
    gateway._materialize_continuation_decision(create_decision, user_id="u1", session_id="s1", message="创建一个写代码 app")

    response = asyncio.run(
        gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1"))
    )

    assert response.type == "progress"
    assert "我已经恢复上次未完成的任务" in response.content
    assert response.requires_input is False
    assert response.data is not None
    assert response.data["pending_task"]["target_ref"]["app_id"].startswith("app_draft_")
    assert response.data["pending_task"]["known_facts"]["runtime_profile"] == "default"
    assert response.data["pending_task"]["known_facts"]["execution_mode"] == "service"
    assert response.data["pending_task"]["status"] == "ready_to_execute"
    assert response.data["pending_task"]["current_stage"] == "implementation_pending"
    assert response.data["pending_task"]["stage_status"] == "completed"


def test_duplicate_create_request_with_existing_open_task_shortcuts_to_continue():
    task = PendingTaskRecord(
        task_id="pt-existing-1",
        user_id="u1",
        intent="create_app",
        status="drafted",
        target_ref={"app_id": "app_draft_existing"},
        next_recommended_action={"type": "continue_draft_app_setup", "app_id": "app_draft_existing"},
    )
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=_PendingTaskStore(task),
    )

    decision = gateway._build_continuation_decision("创建一个笔记 app", task, "sess-1")

    assert decision is not None
    assert decision.conversation_mode == "continue_task"
    assert decision.pending_task_id == "pt-existing-1"
    assert decision.target_ref["app_id"] == "app_draft_existing"


def test_duplicate_create_request_reuses_existing_open_task(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
    )

    decision1 = gateway._build_continuation_decision("创建一个写代码 app", None)
    assert decision1 is not None
    gateway._materialize_continuation_decision(decision1, user_id="u1", session_id="s1", message="创建一个写代码 app")
    existing_task_id = decision1.pending_task_id
    existing_app_id = decision1.target_ref["app_id"]

    latest_task = pending_store.get_latest_open_task("u1")
    decision2 = gateway._build_continuation_decision("创建一个写代码 app", latest_task)
    gateway._materialize_continuation_decision(decision2 or decision1, user_id="u1", session_id="s1", message="创建一个写代码 app")

    assert len(draft_service.list_apps("u1")) == 1
    final_task = pending_store.get_latest_open_task("u1")
    assert final_task is not None
    assert final_task.task_id == existing_task_id
    assert final_task.target_ref["app_id"] == existing_app_id


def test_execute_locate_repo_context_updates_pending_task(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    task = PendingTaskRecord(
        task_id="pt-repo-1",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="repo_locating",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_1"},
        next_recommended_action={"type": "locate_repo_context", "app_id": "app_repo_1"},
        task_list=[{"id": "t1", "module": "app/system/gateway/light_brain_gateway.py"}],
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:locate_repo_context:app_repo_1",
            action_params={"intent": "locate_repo_context", "app_id": "app_repo_1"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    assert response.data["repo_context"]["active_repo_path"] == str(REPO_ROOT)
    assert response.data["repo_context"]["primary_readme_path"] == str(REPO_ROOT / "README.md")
    assert response.data["repo_context"]["repo_valid"] is True
    assert isinstance(response.data["repo_context"]["primary_readme_exists"], bool)
    assert isinstance(response.data["repo_context"]["git_branch"], str)
    assert isinstance(response.data["repo_context"]["git_dirty"], bool)
    updated = pending_store.get_latest_open_task("u1")
    assert updated is not None
    assert updated.current_stage == "implementation_pending"
    assert updated.next_recommended_action["type"] == "implement_app_change"


def test_execute_approve_solution_draft_hands_off_to_tasklist(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    task = PendingTaskRecord(
        task_id="pt-approve-1",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="pending_input",
        current_stage="solution_reviewing",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_start"},
        next_recommended_action={"type": "approve_solution_draft", "app_id": "app_repo_start"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:approve_solution_draft:app_repo_start",
            action_params={"intent": "approve_solution_draft", "app_id": "app_repo_start"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    updated = pending_store.get_latest_open_task("u1")
    assert updated is not None
    assert updated.current_stage == "tasklist_preparing"
    assert updated.next_recommended_action["type"] == "materialize_task_list"


def test_execute_revise_solution_draft_marks_input_required(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    task = PendingTaskRecord(
        task_id="pt-revise-1",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="pending_input",
        current_stage="solution_reviewing",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_start"},
        next_recommended_action={"type": "revise_solution_draft", "app_id": "app_repo_start"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:revise_solution_draft:app_repo_start",
            action_params={"intent": "revise_solution_draft", "app_id": "app_repo_start"},
        )
    )

    assert response.type == "progress"
    assert response.requires_input is True
    updated = pending_store.get_latest_open_task("u1")
    assert updated is not None
    assert updated.stage_status == "blocked"
    assert updated.review_result["decision"] == "revise_required"


def test_execute_materialize_task_list_prepares_repo_handoff(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    task = PendingTaskRecord(
        task_id="pt-tasklist-1",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="tasklist_preparing",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_0"},
        draft_payload={"name": "demo_app"},
        next_recommended_action={"type": "materialize_task_list", "app_id": "app_repo_0"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:materialize_task_list:app_repo_0",
            action_params={"intent": "materialize_task_list", "app_id": "app_repo_0"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    assert len(response.data["task_list"]) == 3
    updated = pending_store.get_latest_open_task("u1")
    assert updated is not None
    assert updated.current_stage == "repo_locating"
    assert updated.next_recommended_action["type"] == "locate_repo_context"


def test_execute_implement_app_change_materializes_plan(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    task = PendingTaskRecord(
        task_id="pt-impl-1",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="implementation_pending",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_3"},
        repo_context={
            "active_repo_path": str(REPO_ROOT),
            "primary_readme_path": str(REPO_ROOT / "README.md"),
            "key_docs": [],
            "target_modules": ["app/system/gateway/light_brain_gateway.py"],
        },
        acceptance_plan={
            "test_probe_commands": [],
            "http_runtime_verification_points": [],
            "success_criteria": [],
            "results": [],
        },
        next_recommended_action={"type": "implement_app_change", "app_id": "app_repo_3"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:implement_app_change:app_repo_3",
            action_params={"intent": "implement_app_change", "app_id": "app_repo_3"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    assert response.data["implementation_plan"]["target_files"] == ["app/system/gateway/light_brain_gateway.py"]
    assert response.data["implementation_plan"]["changed_files_intent"][0]["path"] == "app/system/gateway/light_brain_gateway.py"
    assert response.data["implementation_plan"]["changed_files_intent"][0]["source_hint"] == "repo_context.target_modules"
    assert response.data["implementation_plan"]["work_items"][0]["rationale"].startswith("derived from workflow target module")
    assert response.data["implementation_plan"]["validation_map"][0]["probe"] == "pytest tests/unit/test_light_brain_gateway_pending_task.py -q"
    assert response.data["implementation_plan"]["validation_map"][0]["mapped_work_item_id"] == "work-1"
    updated = pending_store.get_latest_open_task("u1")
    assert updated is not None
    assert updated.current_stage == "acceptance_pending"
    assert updated.next_recommended_action["type"] == "run_acceptance"
    assert updated.acceptance_plan["test_probe_commands"] == ["pytest tests/unit/test_light_brain_gateway_pending_task.py -q"]


def test_execute_implement_app_change_derives_changed_file_intent_from_task_list_when_repo_hints_missing(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    task = PendingTaskRecord(
        task_id="pt-impl-2",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="implementation_pending",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_2"},
        repo_context={
            "active_repo_path": str(REPO_ROOT),
            "primary_readme_path": str(REPO_ROOT / "README.md"),
            "key_docs": [],
            "target_modules": [],
        },
        task_list=[{"id": "t1", "module": "tests/unit/test_http_test_server.py"}],
        next_recommended_action={"type": "implement_app_change", "app_id": "app_repo_2"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:implement_app_change:app_repo_2",
            action_params={"intent": "implement_app_change", "app_id": "app_repo_2"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    assert response.data["implementation_plan"]["changed_files_intent"][0]["path"] == "tests/unit/test_http_test_server.py"
    assert response.data["implementation_plan"]["changed_files_intent"][0]["source_hint"] == "task_list.module"


def test_execute_run_acceptance_records_passed_result(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    task = PendingTaskRecord(
        task_id="pt-accept-1",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="acceptance_running",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_1"},
        repo_context={
            "active_repo_path": str(repo_root),
            "primary_readme_path": str(repo_root / "README.md"),
            "key_docs": [],
            "target_modules": [],
        },
        acceptance_plan={
            "test_probe_commands": ["python3 -c 'print(\"ok\")'"],
            "http_runtime_verification_points": [],
            "success_criteria": ["command exits 0"],
            "results": [],
        },
        next_recommended_action={"type": "run_acceptance", "app_id": "app_repo_1"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:run_acceptance:app_repo_1",
            action_params={"intent": "run_acceptance", "app_id": "app_repo_1"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    assert response.data["acceptance_result"]["status"] == "passed"
    command_evidence = response.data["acceptance_result"]["evidence"]["commands"][0]
    assert command_evidence["exit_code"] == 0
    assert "stdout_excerpt" in command_evidence
    assert "stderr_excerpt" in command_evidence
    assert "ran_at" in command_evidence
    assert isinstance(command_evidence["matched_success_criteria"], list)
    assert command_evidence["matched_work_item_ids"] == []
    assert response.data["acceptance_result"]["evidence"]["summary"]["passed_count"] >= 1
    assert response.data["acceptance_plan"]["evidence_summary"]["passed_count"] >= 1
    updated = pending_store.get_latest_open_task("u1")
    assert updated is None or updated.status == "completed"


def test_execute_run_acceptance_maps_multiple_commands_to_distinct_work_items(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    task = PendingTaskRecord(
        task_id="pt-accept-multi",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="acceptance_running",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_multi"},
        repo_context={
            "active_repo_path": str(repo_root),
            "primary_readme_path": str(repo_root / "README.md"),
            "key_docs": [],
            "target_modules": [],
        },
        implementation_plan={
            "work_items": [
                {"id": "work-1", "target": "app/a.py"},
                {"id": "work-2", "target": "app/b.py"},
            ],
            "validation_map": [
                {"probe": "python3 -c 'print(\"a\")'", "mapped_work_item_id": "work-1"},
                {"probe": "python3 -c 'print(\"b\")'", "mapped_work_item_id": "work-2"},
            ],
        },
        acceptance_plan={
            "test_probe_commands": ["python3 -c 'print(\"a\")'", "python3 -c 'print(\"b\")'"],
            "http_runtime_verification_points": [],
            "success_criteria": ["commands exit 0"],
            "results": [],
        },
        next_recommended_action={"type": "run_acceptance", "app_id": "app_repo_multi"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:run_acceptance:app_repo_multi",
            action_params={"intent": "run_acceptance", "app_id": "app_repo_multi"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    command_results = response.data["acceptance_result"]["evidence"]["commands"]
    assert command_results[0]["matched_work_item_ids"] == ["work-1"]
    assert command_results[1]["matched_work_item_ids"] == ["work-2"]
    assert response.data["acceptance_plan"]["evidence_summary"]["command_count"] == 2
    assert response.data["acceptance_plan"]["change_execution_summary"]["work_item_ids_touched"] == ["work-1", "work-2"]
    assert response.data["acceptance_result"]["evidence"]["change_execution_summary"]["work_item_ids_touched"] == ["work-1", "work-2"]


def test_execute_run_acceptance_records_failed_result(tmp_path: Path):
    updated = pending_store.get_latest_open_task("u1")
    assert updated is None or updated.status == "completed"


def test_execute_run_acceptance_records_failed_result(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    task = PendingTaskRecord(
        task_id="pt-accept-2",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="acceptance_running",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_2"},
        repo_context={
            "active_repo_path": str(repo_root),
            "primary_readme_path": str(repo_root / "README.md"),
            "key_docs": [],
            "target_modules": [],
        },
        acceptance_plan={
            "test_probe_commands": ["python3 -c 'import sys; sys.exit(3)'"],
            "http_runtime_verification_points": [],
            "success_criteria": ["command exits 0"],
            "results": [],
        },
        next_recommended_action={"type": "run_acceptance", "app_id": "app_repo_2"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:run_acceptance:app_repo_2",
            action_params={"intent": "run_acceptance", "app_id": "app_repo_2"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    assert response.data["acceptance_result"]["status"] == "failed"
    command_evidence = response.data["acceptance_result"]["evidence"]["commands"][0]
    assert command_evidence["exit_code"] == 3
    assert command_evidence["status"] == "failed"
    assert response.data["acceptance_result"]["evidence"]["summary"]["failed_count"] == 1
    assert response.data["acceptance_plan"]["evidence_summary"]["failed_count"] == 1
    updated = pending_store.get_latest_open_task("u1")
    assert updated is not None
    assert updated.status == "blocked"
    assert updated.next_recommended_action["type"] == "run_acceptance"


def test_latest_pending_task_selected_when_multiple_tasks_exist(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
    )

    d1 = gateway._build_continuation_decision("创建一个天气 app", None)
    gateway._materialize_continuation_decision(d1, user_id="u1", session_id="s1", message="创建一个天气 app")
    d2 = gateway._build_continuation_decision("创建一个日志 app", None)
    gateway._materialize_continuation_decision(d2, user_id="u1", session_id="s2", message="创建一个日志 app")

    response = asyncio.run(
        gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s2"))
    )

    assert response.data is not None
    assert response.data["pending_task"]["task_id"] == d2.pending_task_id


def test_continue_interception_keeps_structured_payload(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    from app.services.pending_task_orchestrator import PendingTaskOrchestrator
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
        pending_task_orchestrator=PendingTaskOrchestrator(pending_store, draft_service),
    )

    create_decision = gateway._build_continuation_decision("创建一个提醒 app", None)
    gateway._materialize_continuation_decision(create_decision, user_id="u1", session_id="s1", message="创建一个提醒 app")
    response = asyncio.run(
        gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1"))
    )

    assert response.type == "progress"
    assert response.data is not None
    assert "continuation_decision" in response.data
    assert response.data["continuation_decision"]["conversation_mode"] == "continue_task"
    assert response.data["pending_task"]["status"] == "ready_to_execute"


def test_continue_task_writes_back_default_runtime_profile(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    from app.services.pending_task_orchestrator import PendingTaskOrchestrator
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
    )

    create_decision = gateway._build_continuation_decision("创建一个监控 app", None)
    gateway._materialize_continuation_decision(create_decision, user_id="u1", session_id="s1", message="创建一个监控 app")
    gateway._pending_task_orchestrator = PendingTaskOrchestrator(pending_store, draft_service)
    response = asyncio.run(
        gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1"))
    )
    latest_task = pending_store.get_latest_open_task("u1")

    assert response.data is not None
    assert latest_task is not None
    assert latest_task.known_facts["runtime_profile"] == "default"
    assert latest_task.known_facts["execution_mode"] == "service"
    assert latest_task.status == "ready_to_execute"
    assert latest_task.current_stage == "implementation_pending"
    assert latest_task.stage_status == "completed"
    assert latest_task.missing_fields == []


def test_second_continue_consumes_execute_draft_next_action(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    from app.services.pending_task_orchestrator import PendingTaskOrchestrator
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
        pending_task_orchestrator=PendingTaskOrchestrator(pending_store, draft_service),
    )

    create_decision = gateway._build_continuation_decision("创建一个博客 app", None)
    gateway._materialize_continuation_decision(create_decision, user_id="u1", session_id="s1", message="创建一个博客 app")
    asyncio.run(gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1")))
    response = asyncio.run(gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1")))
    latest_task = pending_store.get_latest_open_task("u1")

    assert response.data is not None
    assert latest_task is not None
    assert latest_task.known_facts["draft_setup_prepared"] is True
    assert latest_task.current_stage == "implementation_running"
    assert latest_task.stage_status == "completed"
    assert latest_task.next_recommended_action["type"] == "report_draft_ready"


def test_third_continue_reports_draft_ready_completion(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    from app.services.pending_task_orchestrator import PendingTaskOrchestrator
    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
        pending_task_orchestrator=PendingTaskOrchestrator(pending_store, draft_service),
    )

    create_decision = gateway._build_continuation_decision("创建一个日记 app", None)
    gateway._materialize_continuation_decision(create_decision, user_id="u1", session_id="s1", message="创建一个日记 app")
    asyncio.run(gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1")))
    asyncio.run(gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1")))
    response = asyncio.run(gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1")))

    assert response.data is not None
    assert "草案任务已经准备完成" in response.content
    assert response.data["pending_task"]["status"] == "completed"
    assert response.data["pending_task"]["current_stage"] == "done"
    assert response.data["pending_task"]["stage_status"] == "completed"
    assert response.data["pending_task"]["known_facts"]["draft_ready_reported"] is True
    assert response.data["pending_task"]["known_facts"]["lifecycle_ready_status"] == "compiled"
    assert response.data["pending_task"]["next_recommended_action"]["type"] == "apply_draft_app"
    assert response.data["lifecycle_handoff"]["handoff_target"] == "AppApplicationService"
    assert response.data["lifecycle_handoff"]["recommended_intent"] == "apply_draft_app"
    assert response.related_app == response.data["pending_task"]["target_ref"]["app_id"]
    assert response.actions[0].payload["intent"] == "apply_draft_app"
    app_id = response.data["pending_task"]["target_ref"]["app_id"]
    assert draft_service.get_app(app_id).status == "compiled"


def test_continue_response_exposes_future_workflow_action_contract(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    from app.system.runtime.pending_task_store import PendingTaskStore

    pending_store = PendingTaskStore(runtime_store)
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        pending_task_store=pending_store,
    )
    task = PendingTaskRecord(
        task_id="pt-future-1",
        user_id="u1",
        session_id="s1",
        intent="继续推进应用改动",
        status="ready_to_execute",
        current_stage="solution_reviewing",
        stage_status="in_progress",
        target_ref={"app_id": "app_future_demo", "target_id": "app_future_demo"},
        next_recommended_action={"type": "approve_solution_draft"},
    )

    response = gateway._build_continue_task_response(
        "s1",
        task,
        TaskContinuationDecision(conversation_mode="continue_task", pending_task_id="pt-future-1"),
    )

    assert response.actions[0].payload["intent"] == "approve_solution_draft"
    assert response.actions[0].payload["app_id"] == "app_future_demo"
    assert "当前阶段：solution_reviewing (in_progress)" in response.content



def test_execute_action_apply_draft_app_routes_to_application_layer(tmp_path: Path):
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
    draft_service = DraftAppService(runtime_store)
    lifecycle = AppLifecycleService(runtime_store)
    runtime_host = AppRuntimeHostService(lifecycle=lifecycle, store=runtime_store)
    from app.system.runtime.pending_task_store import PendingTaskStore
    from app.services.pending_task_orchestrator import PendingTaskOrchestrator

    pending_store = PendingTaskStore(runtime_store)
    app_application_service = AppApplicationService(
        draft_app_application_service=DraftAppApplicationService(draft_service, lifecycle, runtime_host)
    )
    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        draft_app_service=draft_service,
        pending_task_store=pending_store,
        pending_task_orchestrator=PendingTaskOrchestrator(pending_store, draft_service),
        app_application_service=app_application_service,
    )

    create_decision = gateway._build_continuation_decision("创建一个笔记 app", None)
    gateway._materialize_continuation_decision(create_decision, user_id="u1", session_id="s1", message="创建一个笔记 app")
    asyncio.run(gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1")))
    asyncio.run(gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1")))
    final_response = asyncio.run(gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="s1")))
    app_id = final_response.data["pending_task"]["target_ref"]["app_id"]

    action_response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="s1",
            action_id=f"apply-draft:{app_id}",
            action_params={"intent": "apply_draft_app", "app_id": app_id},
        )
    )

    assert action_response.type == "progress"
    assert action_response.related_app == app_id
    assert lifecycle.get_instance(app_id).status == "running"
    assert action_response.data["lifecycle_transition"] == "draft_to_running_activation"
    assert "推进到可运行状态" in action_response.content
