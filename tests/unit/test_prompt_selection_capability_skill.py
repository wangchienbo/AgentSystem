from app.api.main import skill_control, skill_runtime, log_evidence
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
            inputs={"operation": "evidence_search", "query": "workflow", "limit": 5},
        )
    )

    assert result.status == "completed"
    assert "items" in result.output
    assert len(result.output["items"]) >= 1
