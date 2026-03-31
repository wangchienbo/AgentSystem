from app.api.main import skill_control, skill_runtime
from app.models.skill_runtime import SkillExecutionRequest


APP_ID = "app.capability.demo"
WF_ID = "wf.capability.demo"
STEP_ID = "step.capability.demo"



def test_workflow_and_risk_capability_skills_are_registered() -> None:
    skill_ids = {item.skill_id for item in skill_control.list_skills()}
    assert "workflow.insight.skill" in skill_ids
    assert "risk.governance.skill" in skill_ids



def test_workflow_insight_capability_skill_executes_stats() -> None:
    result = skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="workflow.insight.skill",
            app_instance_id=APP_ID,
            workflow_id=WF_ID,
            step_id=STEP_ID,
            inputs={"operation": "stats"},
        )
    )

    assert result.status == "completed"
    assert "total_executions" in result.output



def test_risk_governance_capability_skill_executes_stats_and_events() -> None:
    stats = skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="risk.governance.skill",
            app_instance_id=APP_ID,
            workflow_id=WF_ID,
            step_id=STEP_ID,
            inputs={"operation": "stats"},
        )
    )
    events = skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="risk.governance.skill",
            app_instance_id=APP_ID,
            workflow_id=WF_ID,
            step_id=f"{STEP_ID}.events",
            inputs={"operation": "events"},
        )
    )

    assert stats.status == "completed"
    assert events.status == "completed"
    assert "total_events" in stats.output
    assert "items" in events.output
