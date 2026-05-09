from __future__ import annotations

import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from app.models.pending_task import PendingTaskRecord
from app.persistence.runtime_state_store import RuntimeStateStore
from app.services.light_brain_memory import LightBrainMemory
from app.system.gateway.light_brain_gateway import LightBrainGateway


class _Interpreter:
    def interpret(self, message, available_apps, user_id, session_id):
        from app.models.chat import InterpretedCommand

        return InterpretedCommand(intent="greet", raw_input=message, user_id=user_id)


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
    assert response.data["implementation_plan"]["validation_map"][0]["changed_file_paths"] == ["app/system/gateway/light_brain_gateway.py"]
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
    assert response.data["implementation_plan"]["validation_map"][0]["changed_file_paths"] == ["tests/unit/test_http_test_server.py"]


def test_execute_implement_app_change_normalizes_repo_absolute_target_modules(tmp_path: Path):
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
    abs_module = repo_root / "app/system/gateway/light_brain_gateway.py"
    task = PendingTaskRecord(
        task_id="pt-impl-abs",
        user_id="u1",
        session_id="sess-1",
        intent="create_app",
        status="ready_to_execute",
        current_stage="implementation_pending",
        stage_status="in_progress",
        target_ref={"app_id": "app_repo_abs"},
        repo_context={
            "active_repo_path": str(repo_root),
            "primary_readme_path": str(repo_root / "README.md"),
            "key_docs": [],
            "target_modules": [str(abs_module)],
        },
        acceptance_plan={
            "test_probe_commands": [],
            "http_runtime_verification_points": [],
            "success_criteria": [],
            "results": [],
        },
        next_recommended_action={"type": "implement_app_change", "app_id": "app_repo_abs"},
    )
    pending_store.upsert_task(task)

    response = asyncio.run(
        gateway.execute_action(
            user_id="u1",
            session_id="sess-1",
            action_id="workflow-action:implement_app_change:app_repo_abs",
            action_params={"intent": "implement_app_change", "app_id": "app_repo_abs"},
        )
    )

    assert response.type == "progress"
    assert response.data is not None
    assert response.data["implementation_plan"]["repo_path"] == str(repo_root)
    assert response.data["implementation_plan"]["target_files"] == ["app/system/gateway/light_brain_gateway.py"]
    assert response.data["implementation_plan"]["changed_files_intent"][0]["path"] == "app/system/gateway/light_brain_gateway.py"
    assert response.data["implementation_plan"]["validation_map"][0]["changed_file_paths"] == ["app/system/gateway/light_brain_gateway.py"]


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
