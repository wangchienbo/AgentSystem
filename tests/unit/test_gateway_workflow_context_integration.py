from __future__ import annotations

import asyncio

from app.models.chat import ChatMessageRequest
from app.models.context import SessionContextRecord, SessionNode
from app.models.pending_task import PendingTaskRecord
from app.services.context_center import ContextCenter
from app.services.light_brain_memory import LightBrainMemory
from app.services.pending_task_orchestrator import PendingTaskOrchestrator
from app.system.gateway.light_brain_gateway import LightBrainGateway
from app.system.invocation.context_bundle_assembly import ContextBundleAssemblyService
from app.system.invocation.tool_context_contract import ToolContextQueryRequest
from app.system.invocation.tool_context_runtime import ToolContextRuntime


class _Interpreter:
    def interpret(self, message, available_apps, user_id, session_id):
        from app.models.chat import InterpretedCommand

        return InterpretedCommand(intent="greet", raw_input=message, user_id=user_id)


class _PendingTaskStore:
    def __init__(self, task: PendingTaskRecord | None):
        self.task = task

    def get_latest_open_task(self, user_id):
        return self.task if user_id == "u1" else None

    def upsert_task(self, task):
        self.task = task
        return task


def test_gateway_workflow_and_context_center_integration_emits_stage_and_acceptance_hooks(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path / "context")
    store = _PendingTaskStore(
        PendingTaskRecord(
            task_id="pt-int-1",
            user_id="u1",
            session_id="sess-1",
            intent="create_app",
            status="pending_input",
            current_stage="solution_reviewing",
            stage_status="pending",
            next_recommended_action={"type": "approve_solution_draft"},
        )
    )
    orchestrator = PendingTaskOrchestrator(store, context_center=center)

    task = orchestrator.mark_stage_in_progress(
        store.task,
        stage="tasklist_preparing",
        next_action={"type": "materialize_task_list"},
    )
    task = orchestrator.mark_stage_completed(
        task,
        stage="tasklist_preparing",
        next_stage="repo_locating",
        status="ready_to_execute",
        next_action={"type": "locate_repo_context"},
    )
    orchestrator.capture_acceptance_plan(
        task,
        test_probe_commands=["pytest -q"],
        http_runtime_verification_points=["GET /health returns 200"],
        success_criteria=["tests pass"],
    )
    orchestrator.capture_acceptance_result(
        task,
        status="passed",
        summary="acceptance passed",
        evidence={"command": "pytest -q"},
    )

    messages = [item.message for item in center.read_detail_events("sess-1")]
    assert "workflow_hook event=stage_entered stage=tasklist_preparing action=materialize_task_list" in messages
    assert "workflow_hook event=stage_completed stage=repo_locating action=locate_repo_context" in messages
    assert "workflow_hook event=acceptance_started stage=repo_locating" in messages
    assert "acceptance_result status=passed summary=acceptance passed" in messages
    assert "workflow_hook event=acceptance_completed stage=repo_locating" in messages


def test_context_bundle_summary_first_and_detail_retrieval_stay_compatible(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path / "context")
    center.register_session_node(SessionNode(session_id="sess-2", user_id="u1", channel="test"))
    center.register_asset_local_session("asset:demo:v1", "local-1", "sess-2")
    center.append_context(SessionContextRecord(session_id="sess-2", kind="summary", role="system", content="formal summary"))
    center.append_context(SessionContextRecord(session_id="sess-2", kind="message", role="user", content="detail-a"))
    center.append_context(SessionContextRecord(session_id="sess-2", kind="tool_result", role="tool", content="asset detail payload", metadata={"evidence_ref": "asset-1"}))

    assembly = ContextBundleAssemblyService(center, per_record_token_estimate=50)
    runtime = ToolContextRuntime(center, assembly)

    bundle = runtime.assemble_for_model(
        asset_id="asset:demo:v1",
        local_session_id="local-1",
        query="show me the context",
        token_budget=100,
        recent_limit=3,
    )
    first_ref = (
        bundle["summary"][0].get("record_id")
        if bundle["summary"]
        else bundle["recent"][0]["record_id"]
    )
    detail = center.get_detail_record_by_reference("sess-2", "detail:sess-2:1")
    evidence = center.query_evidence_refs("asset:demo:v1", "local-1")

    assert bundle["trace_metadata"]["summary_first"] is True
    assert bundle["summary"] or bundle["recent"]
    if first_ref is not None:
        assert first_ref.startswith("summary:sess-2:") or first_ref.startswith("detail:sess-2:")
    assert detail is not None
    assert detail["message"] == "detail-a"
    assert evidence[-1]["metadata"]["evidence_ref"] == "asset-1"


def test_gateway_continue_response_keeps_context_view_and_workflow_payload(tmp_path) -> None:
    center = ContextCenter(base_dir=tmp_path / "context")
    center.register_session_node(SessionNode(session_id="sess-3", user_id="u1", channel="test"))
    center.append_context(SessionContextRecord(session_id="sess-3", kind="message", role="user", content="create app draft"))
    center.append_pending_buffer_event("sess-3", {"timestamp": "2099-05-04T18:00:00Z", "role": "assistant", "message": "pending-next-step"})

    gateway = LightBrainGateway(
        memory=LightBrainMemory(),
        interpreter=_Interpreter(),
        context_center=center,
        pending_task_store=_PendingTaskStore(None),
    )

    response = asyncio.run(
        gateway.receive_message(ChatMessageRequest(user_id="u1", channel="test", message="继续", session_id="sess-3"))
    )

    assert response.type == "progress"
    assert response.data is not None
    assert response.data["continuation_decision"]["next_action"]["type"] == "resume_from_context_center"
    assert "Context Center" in response.content
