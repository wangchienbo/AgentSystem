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



def _build_service(tmp_path):
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
    compaction = ContextCompactionService(
        app_context_store=context_store,
        workflow_executor=_StubWorkflowExecutor(),
        store=store,
        log_evidence_service=evidence,
    )
    service = PromptSelectionService(context_compaction=compaction, log_evidence=evidence)
    return service, evidence



def test_prompt_selection_prefers_working_set_and_indexed_evidence(tmp_path) -> None:
    service, evidence = _build_service(tmp_path)
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

    result = service.select_for_prompt("app.prompt", limit=3)

    assert result["working_set"]["layer"] == "working_set"
    assert result["selection_policy"]["avoid_raw_history"] is True
    assert result["selection_policy"]["budget_mode"] == "count_only"
    assert len(result["selected_evidence"]) >= 1
    assert result["selection_summary"]["selected_count"] >= 1
    assert "assembled_prompt" in result
    assert "[WORKING SET]" in result["assembled_prompt"]



def test_prompt_selection_respects_token_budget(tmp_path) -> None:
    service, evidence = _build_service(tmp_path)
    for idx in range(3):
        evidence.ingest_workflow_failure(
            app_instance_id="app.prompt",
            workflow_id=f"wf.{idx}",
            failed_step_ids=["step.a"],
            execution_id=f"exec.{idx}.1",
            status="partial",
        )
        evidence.ingest_workflow_failure(
            app_instance_id="app.prompt",
            workflow_id=f"wf.{idx}",
            failed_step_ids=["step.a"],
            execution_id=f"exec.{idx}.2",
            status="partial",
        )
        evidence.ingest_workflow_failure(
            app_instance_id="app.prompt",
            workflow_id=f"wf.{idx}",
            failed_step_ids=["step.a"],
            execution_id=f"exec.{idx}.3",
            status="partial",
        )

    result = service.select_for_prompt(
        "app.prompt",
        limit=5,
        max_prompt_tokens=800,
        reserved_output_tokens=200,
        working_set_token_estimate=400,
        per_evidence_token_estimate=120,
    )

    assert result["prompt_budget"]["mode"] == "token_aware"
    assert result["prompt_budget"]["available_input_tokens"] == 200
    assert result["prompt_budget"]["selected_limit"] == 1
    assert result["prompt_budget"]["truncated_by_budget"] is True
    assert len(result["selected_evidence"]) == 1



def test_prompt_selection_search_returns_ranked_policy_metadata(tmp_path) -> None:
    service, evidence = _build_service(tmp_path)
    evidence.ingest_workflow_failure(
        app_instance_id="app.prompt",
        workflow_id="wf.workflow",
        failed_step_ids=["step.a"],
        execution_id="exec.workflow.1",
        status="partial",
    )
    evidence.ingest_workflow_failure(
        app_instance_id="app.prompt",
        workflow_id="wf.workflow",
        failed_step_ids=["step.a"],
        execution_id="exec.workflow.2",
        status="partial",
    )
    evidence.ingest_workflow_failure(
        app_instance_id="app.prompt",
        workflow_id="wf.workflow",
        failed_step_ids=["step.a"],
        execution_id="exec.workflow.3",
        status="partial",
    )

    result = service.search_evidence(query="workflow", app_instance_id="app.prompt", limit=5, strategy="query_first")

    assert result["retrieval_policy"]["ranking_strategy"] == "query_first"
    assert result["meta"]["returned_count"] >= 1
    assert result["items"][0]["match_score"] >= 1
    assert "rank_score" in result["items"][0]



def test_prompt_selection_prefers_promoted_evidence_over_signal(tmp_path) -> None:
    service, evidence = _build_service(tmp_path)
    for idx in range(3):
        evidence.ingest_workflow_failure(
            app_instance_id="app.prompt",
            workflow_id="wf.promoted",
            failed_step_ids=["step.a"],
            execution_id=f"exec.promoted.{idx}",
            status="partial",
        )
    evidence.ingest_policy_event(skill_id="skill.demo", event_type="policy_blocked", reason="blocked once", scope="generated_app_assembly")
    evidence.ingest_policy_event(skill_id="skill.demo", event_type="policy_blocked", reason="blocked twice", scope="generated_app_assembly")

    result = service.search_evidence(query="workflow", app_instance_id="app.prompt", limit=5, strategy="balanced")

    assert len(result["items"]) >= 1
    assert result["items"][0]["source_type"] == "evidence"



def test_prompt_selection_can_disable_prompt_assembly(tmp_path) -> None:
    service, evidence = _build_service(tmp_path)
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

    result = service.select_for_prompt("app.prompt", limit=3, include_prompt_assembly=False)

    assert "prompt_sections" in result
    assert "assembled_prompt" not in result
