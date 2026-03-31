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
        return {
            "id": "resp_123",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "good normalized output"}]}],
            "extra_payload": extra_payload,
        }


from app.services.collection_policy_service import CollectionPolicyService
from app.services.evaluation_summary_service import EvaluationSummaryService
from app.services.telemetry_service import TelemetryService
from app.services.upgrade_log_service import UpgradeLogService
from app.services.skill_risk_policy import SkillRiskPolicyService


class _JsonFakeClient:
    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def request(self, input_payload, *, extra_payload=None):
        return {
            "id": "resp_json_123",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"ok": true}'}]}],
            "extra_payload": extra_payload,
        }


class _BulletListFakeClient:
    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def request(self, input_payload, *, extra_payload=None):
        return {
            "id": "resp_list_123",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": '- first\n- second\n- third'}]}],
            "extra_payload": extra_payload,
        }


class _KeyValueFakeClient:
    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def request(self, input_payload, *, extra_payload=None):
        return {
            "id": "resp_kv_123",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": 'name: alice\nrole: admin'}]}],
            "extra_payload": extra_payload,
        }


class _ApprovalFakeClient:
    def __init__(self, config, api_key):
        self.config = config
        self.api_key = api_key

    def request(self, input_payload, *, extra_payload=None):
        return {
            "id": "resp_approval_123",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": 'APPROVED: risk acceptable'}]}],
            "extra_payload": extra_payload,
        }



def _build_invocation(tmp_path, app_instance_id: str, client_factory):
    store = RuntimeStateStore(base_dir=str(tmp_path / (app_instance_id.replace('.', '-') + "-store")))
    lifecycle = AppLifecycleService(store=store)
    context_store = AppContextStore(lifecycle=lifecycle, store=store)
    evidence = LogEvidenceService(store=store)
    policy_service = CollectionPolicyService(store=store)
    upgrade_log_service = UpgradeLogService(base_dir=str(tmp_path / (app_instance_id.replace('.', '-') + "-logs")))
    telemetry = TelemetryService(store=store, policy_service=policy_service, upgrade_log_service=upgrade_log_service)
    evaluation = EvaluationSummaryService(store=store, upgrade_log_service=upgrade_log_service)
    risk_policy = SkillRiskPolicyService(store=store, log_evidence_service=evidence)
    context_store._contexts[app_instance_id] = AppSharedContext(
        app_instance_id=app_instance_id,
        app_name=f"bp.{app_instance_id}",
        owner_user_id=f"user.{app_instance_id}",
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
        client_factory=client_factory,
        telemetry_service=telemetry,
        evaluation_summary_service=evaluation,
        skill_risk_policy_service=risk_policy,
    )
    evidence.ingest_workflow_failure(
        app_instance_id=app_instance_id,
        workflow_id="wf.prompt",
        failed_step_ids=["step.a"],
        execution_id="exec.1",
        status="partial",
    )
    evidence.ingest_workflow_failure(
        app_instance_id=app_instance_id,
        workflow_id="wf.prompt",
        failed_step_ids=["step.a"],
        execution_id="exec.2",
        status="partial",
    )
    return invocation, telemetry, evaluation, risk_policy



def test_prompt_invocation_service_invokes_model_with_assembled_prompt(tmp_path) -> None:
    invocation, telemetry, evaluation, risk_policy = _build_invocation(tmp_path, "app.prompt", _FakeClient)

    result = invocation.invoke_with_selection(
        app_instance_id="app.prompt",
        query="workflow",
        limit=3,
        strategy="query_first",
        extra_payload={
            "metadata": {"source": "test"},
            "feedback": {"score": 5},
            "workflow_outcome": "success",
            "expected_output": "slug_text",
            "retry_count": 0,
        },
    )

    assert "assembled_prompt" in result
    assert result["model_invocation"]["provider"] == "OpenAI"
    assert result["model_invocation"]["result"]["id"] == "resp_123"
    assert result["model_invocation"]["result"]["extra_payload"]["metadata"] == {"source": "test"}
    assert result["model_invocation"]["result"]["extra_payload"]["expected_output"] == "slug_text"
    assert "normalized_response" in result
    assert result["normalized_response"]["finish_status"] == "completed"
    assert result["normalized_response"]["estimated_output_tokens"] >= 0
    assert "quality_signals" in result
    assert result["quality_signals"]["empty_text"] is False
    assert result["invocation_meta"]["interaction_id"].startswith("prompt_invoke:")
    assert telemetry.get_interaction(result["invocation_meta"]["interaction_id"]) is not None
    assert len(telemetry.list_steps(result["invocation_meta"]["interaction_id"])) == 1
    evaluation_record = evaluation.get(f"prompt-invoke:{result['invocation_meta']['interaction_id']}")
    assert evaluation_record is not None
    assert evaluation_record.feedback_delta > 0
    assert evaluation_record.success_delta > 0
    assert result["quality_signals"]["schema_expectation"] == "slug_text"
    assert result["quality_signals"]["schema_satisfied"] is False
    events = risk_policy.list_events(skill_id="prompt.invoke")
    assert any(item.scope == "prompt_invocation" for item in events)



def test_prompt_invocation_quality_signals_can_satisfy_expected_json_shape(tmp_path) -> None:
    invocation, _, evaluation, _ = _build_invocation(tmp_path, "app.prompt.json", _JsonFakeClient)

    result = invocation.invoke_with_selection(
        app_instance_id="app.prompt.json",
        query="workflow",
        limit=3,
        strategy="query_first",
        extra_payload={
            "expected_output": "json_object",
            "workflow_outcome": "success",
        },
    )

    assert result["quality_signals"]["schema_expectation"] == "json_object"
    assert result["quality_signals"]["schema_satisfied"] is True
    evaluation_record = evaluation.get(f"prompt-invoke:{result['invocation_meta']['interaction_id']}")
    assert evaluation_record is not None
    assert evaluation_record.success_delta > 0



def test_prompt_invocation_quality_signals_support_bullet_list(tmp_path) -> None:
    invocation, _, evaluation, _ = _build_invocation(tmp_path, "app.prompt.list", _BulletListFakeClient)

    result = invocation.invoke_with_selection(
        app_instance_id="app.prompt.list",
        query="workflow",
        limit=3,
        strategy="query_first",
        extra_payload={"expected_output": "bullet_list", "workflow_outcome": "success"},
    )

    assert result["quality_signals"]["schema_expectation"] == "bullet_list"
    assert result["quality_signals"]["schema_satisfied"] is True
    evaluation_record = evaluation.get(f"prompt-invoke:{result['invocation_meta']['interaction_id']}")
    assert evaluation_record is not None
    assert evaluation_record.success_delta > 0



def test_prompt_invocation_quality_signals_support_key_value(tmp_path) -> None:
    invocation, _, evaluation, _ = _build_invocation(tmp_path, "app.prompt.kv", _KeyValueFakeClient)

    result = invocation.invoke_with_selection(
        app_instance_id="app.prompt.kv",
        query="workflow",
        limit=3,
        strategy="query_first",
        extra_payload={"expected_output": "key_value", "workflow_outcome": "success"},
    )

    assert result["quality_signals"]["schema_expectation"] == "key_value"
    assert result["quality_signals"]["schema_satisfied"] is True
    evaluation_record = evaluation.get(f"prompt-invoke:{result['invocation_meta']['interaction_id']}")
    assert evaluation_record is not None
    assert evaluation_record.success_delta > 0



def test_prompt_invocation_quality_signals_support_approval_decision(tmp_path) -> None:
    invocation, _, evaluation, _ = _build_invocation(tmp_path, "app.prompt.approval", _ApprovalFakeClient)

    result = invocation.invoke_with_selection(
        app_instance_id="app.prompt.approval",
        query="workflow",
        limit=3,
        strategy="query_first",
        extra_payload={"expected_output": "approval_decision", "workflow_outcome": "success"},
    )

    assert result["quality_signals"]["schema_expectation"] == "approval_decision"
    assert result["quality_signals"]["schema_satisfied"] is True
    evaluation_record = evaluation.get(f"prompt-invoke:{result['invocation_meta']['interaction_id']}")
    assert evaluation_record is not None
    assert evaluation_record.success_delta > 0
