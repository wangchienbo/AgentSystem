import app.bootstrap.skills as builtin_skills
from app.api.main import app_context_store, log_evidence, skill_control, skill_runtime
from app.models.app_context import AppSharedContext
from app.models.skill_runtime import SkillExecutionRequest


APP_ID = "app.prompt.demo"
WF_ID = "wf.prompt.demo"
STEP_ID = "step.prompt.demo"



def test_prompt_selection_skill_is_registered() -> None:
    skill_ids = {item.skill_id for item in skill_control.list_skills()}
    assert "prompt.selection.skill" in skill_ids



def test_prompt_selection_skill_executes_evidence_search() -> None:
    log_evidence.ingest_workflow_failure(
        app_instance_id=APP_ID,
        workflow_id="wf.demo",
        failed_step_ids=["step.a"],
        execution_id="exec.1",
        status="partial",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id=APP_ID,
        workflow_id="wf.demo",
        failed_step_ids=["step.a"],
        execution_id="exec.2",
        status="partial",
    )

    result = skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="prompt.selection.skill",
            app_instance_id=APP_ID,
            workflow_id=WF_ID,
            step_id=STEP_ID,
            inputs={"operation": "evidence_search", "query": "workflow", "limit": 5, "strategy": "query_first"},
        )
    )

    assert result.status == "completed"
    assert "items" in result.output
    assert len(result.output["items"]) >= 1
    assert "retrieval_policy" in result.output
    assert result.output["retrieval_policy"]["ranking_strategy"] == "query_first"



def test_prompt_selection_skill_executes_budget_aware_select() -> None:
    app_context_store._contexts[APP_ID] = AppSharedContext(
        app_instance_id=APP_ID,
        app_name="bp.prompt.demo",
        owner_user_id="user.prompt.demo",
        description="prompt skill context",
        status="active",
        current_goal="answer user",
        current_stage="reasoning",
        entries=[],
    )
    for idx in range(3):
        log_evidence.ingest_workflow_failure(
            app_instance_id=APP_ID,
            workflow_id=f"wf.select.{idx}",
            failed_step_ids=["step.a"],
            execution_id=f"exec.select.{idx}.1",
            status="partial",
        )
        log_evidence.ingest_workflow_failure(
            app_instance_id=APP_ID,
            workflow_id=f"wf.select.{idx}",
            failed_step_ids=["step.a"],
            execution_id=f"exec.select.{idx}.2",
            status="partial",
        )
        log_evidence.ingest_workflow_failure(
            app_instance_id=APP_ID,
            workflow_id=f"wf.select.{idx}",
            failed_step_ids=["step.a"],
            execution_id=f"exec.select.{idx}.3",
            status="partial",
        )

    result = skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="prompt.selection.skill",
            app_instance_id=APP_ID,
            workflow_id=WF_ID,
            step_id=STEP_ID,
            inputs={
                "operation": "select",
                "query": "workflow",
                "limit": 5,
                "max_prompt_tokens": 800,
                "reserved_output_tokens": 200,
                "working_set_token_estimate": 400,
                "per_evidence_token_estimate": 120,
                "strategy": "balanced",
                "include_prompt_assembly": True,
            },
        )
    )

    assert result.status == "completed"
    assert result.output["prompt_budget"]["mode"] == "token_aware"
    assert result.output["prompt_budget"]["selected_limit"] == 1
    assert len(result.output["selected_evidence"]) == 1
    assert "assembled_prompt" in result.output
    assert result.output["selection_policy"]["ranking_strategy"] == "balanced"



def test_prompt_selection_skill_can_invoke_model_ready_prompt(monkeypatch) -> None:
    app_context_store._contexts[APP_ID] = AppSharedContext(
        app_instance_id=APP_ID,
        app_name="bp.prompt.demo",
        owner_user_id="user.prompt.demo",
        description="prompt skill context",
        status="active",
        current_goal="answer user",
        current_stage="reasoning",
        entries=[],
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id=APP_ID,
        workflow_id="wf.model.ready",
        failed_step_ids=["step.a"],
        execution_id="exec.model.ready.1",
        status="partial",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id=APP_ID,
        workflow_id="wf.model.ready",
        failed_step_ids=["step.a"],
        execution_id="exec.model.ready.2",
        status="partial",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id=APP_ID,
        workflow_id="wf.model.ready",
        failed_step_ids=["step.a"],
        execution_id="exec.model.ready.3",
        status="partial",
    )

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

    monkeypatch.setattr(builtin_skills, "ModelConfigLoader", _FakeLoader)
    monkeypatch.setattr(builtin_skills, "OpenAIResponsesClient", _FakeClient)

    result = skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="prompt.selection.skill",
            app_instance_id=APP_ID,
            workflow_id=WF_ID,
            step_id=STEP_ID,
            inputs={
                "operation": "model_ready_prompt",
                "query": "workflow",
                "limit": 3,
                "strategy": "query_first",
                "include_prompt_assembly": True,
            },
        )
    )

    assert result.status == "completed"
    assert "model_invocation" in result.output
    assert result.output["model_invocation"]["provider"] == "OpenAI"
    assert result.output["model_invocation"]["result"]["id"] == "resp_123"
    assert "assembled_prompt" in result.output
