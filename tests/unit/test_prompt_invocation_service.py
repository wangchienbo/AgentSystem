from app.models.app_context import AppSharedContext
from app.services.app_context_store import AppContextStore
from app.services.context_compaction import ContextCompactionService
from app.services.lifecycle import AppLifecycleService
from app.services.log_evidence_service import LogEvidenceService
from app.services.prompt_invocation_service import PromptInvocationService
from app.services.prompt_selection_service import PromptSelectionService
from app.services.runtime_state_store import RuntimeStateStore


class _StubWorkflowExecutor:
    def __init__(self) -> None:
        self._skill_runtime = None

    def list_history(self, app_instance_id: str):
        return []


class _FakeLoader:
    def load(self):
        class _Config:
            provider = "OpenAI"
            model = "gpt-5.4"
        return _Config()

    def resolve_api_key(self, config):
        return "sk-test"


class _FakeClient:
    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def request(self, input_payload, *, extra_payload=None):
        return {"id": "resp_123", "input_echo": input_payload, "extra_payload": extra_payload}



from app.services.collection_policy_service import CollectionPolicyService
from app.services.evaluation_summary_service import EvaluationSummaryService
from app.services.telemetry_service import TelemetryService
from app.services.upgrade_log_service import UpgradeLogService


def test_prompt_invocation_service_invokes_model_with_assembled_prompt(tmp_path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "prompt-invocation-store"))
    lifecycle = AppLifecycleService(store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store)
    evidence = LogEvidenceService(store=store)
    policy_service = CollectionPolicyService(store=store)
    upgrade_log_service = UpgradeLogService(base_dir=str(tmp_path / "prompt-invocation-logs"))
    telemetry = TelemetryService(store=store, policy_service=policy_service, upgrade_log_service=upgrade_log_service)
    evaluation = EvaluationSummaryService(store=store, upgrade_log_service=upgrade_log_service)
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
    selection = PromptSelectionService(context_compaction=compaction, log_evidence=evidence)
    invocation = PromptInvocationService(
        prompt_selection=selection,
        model_loader=_FakeLoader(),
        client_factory=_FakeClient,
        telemetry_service=telemetry,
        evaluation_summary_service=evaluation,
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

    result = invocation.invoke_with_selection(
        app_instance_id="app.prompt",
        query="workflow",
        limit=3,
        strategy="query_first",
        extra_payload={"metadata": {"source": "test"}},
    )

    assert "assembled_prompt" in result
    assert result["model_invocation"]["provider"] == "OpenAI"
    assert result["model_invocation"]["result"]["id"] == "resp_123"
    assert result["model_invocation"]["result"]["extra_payload"] == {"metadata": {"source": "test"}}
    assert "normalized_response" in result
    assert result["normalized_response"]["finish_status"] == "completed"
    assert result["normalized_response"]["estimated_output_tokens"] >= 0
    assert result["invocation_meta"]["interaction_id"].startswith("prompt_invoke:")
    assert telemetry.get_interaction(result["invocation_meta"]["interaction_id"]) is not None
    assert len(telemetry.list_steps(result["invocation_meta"]["interaction_id"])) == 1
    assert evaluation.get(f"prompt-invoke:{result['invocation_meta']['interaction_id']}") is not None
