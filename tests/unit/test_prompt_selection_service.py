from app.models.app_context import AppSharedContext
from app.services.app_context_store import AppContextStore
from app.services.context_compaction import ContextCompactionService
from app.services.lifecycle import AppLifecycleService
from app.services.log_evidence_service import LogEvidenceService
from app.services.prompt_selection_service import PromptSelectionService
from app.services.runtime_state_store import RuntimeStateStore


class _StubWorkflowExecutor:
    def __init__(self) -> None:
        self._skill_runtime = None

    def list_history(self, app_instance_id: str):
        return []



def test_prompt_selection_prefers_working_set_and_indexed_evidence(tmp_path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "prompt-selection-store"))
    lifecycle = AppLifecycleService(store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store)
    evidence = LogEvidenceService(store=store)
    context_store._contexts["app.prompt"] = AppSharedContext(
        app_instance_id="app.prompt",
        app_name="bp.prompt",
        owner_user_id="user.prompt",
        description="prompt context",
        status="active",
        current_goal="answer user",
        current_stage="reasoning",
        entries=[],
    )
    evidence.ingest_workflow_failure(
        app_instance_id="app.prompt",
        workflow_id="wf.prompt",
        failed_step_ids=["step.a"],
        execution_id="exec.1",
        status="partial",
    )
    evidence.ingest_workflow_failure(
        app_instance_id="app.prompt",
        workflow_id="wf.prompt",
        failed_step_ids=["step.a"],
        execution_id="exec.2",
        status="partial",
    )
    compaction = ContextCompactionService(
        app_context_store=context_store,
        workflow_executor=_StubWorkflowExecutor(),
        store=store,
        log_evidence_service=evidence,
    )
    service = PromptSelectionService(context_compaction=compaction, log_evidence=evidence)

    result = service.select_for_prompt("app.prompt", limit=3)

    assert result["working_set"]["layer"] == "working_set"
    assert result["selection_policy"]["avoid_raw_history"] is True
    assert len(result["selected_evidence"]) >= 1
