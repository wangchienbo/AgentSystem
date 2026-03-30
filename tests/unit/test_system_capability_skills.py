from app.api.main import skill_control, skill_runtime
from app.models.skill_runtime import SkillExecutionRequest


APP_ID = "app.capability.demo"
WF_ID = "wf.capability.demo"
STEP_ID = "step.capability.demo"



def test_system_capability_skills_are_registered() -> None:
    skill_ids = {item.skill_id for item in skill_control.list_skills()}
    assert "requirement.skill" in skill_ids
    assert "evidence.skill" in skill_ids
    assert "context.compaction.skill" in skill_ids


def test_requirement_capability_skill_executes() -> None:
    result = skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="requirement.skill",
            app_instance_id=APP_ID,
            workflow_id=WF_ID,
            step_id=STEP_ID,
            inputs={"operation": "readiness", "text": "做一个长期 AI 战略架构规划"},
        )
    )

    assert result.status == "completed"
    assert result.output["readiness"] in {"needs_clarification", "conflicting_constraints", "needs_demo", "ready"}
    assert "requirement_type" in result.output



def test_evidence_capability_skill_executes() -> None:
    result = skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="evidence.skill",
            app_instance_id=APP_ID,
            workflow_id=WF_ID,
            step_id=STEP_ID,
            inputs={"operation": "stats"},
        )
    )

    assert result.status == "completed"
    assert "signal_count" in result.output



def test_context_compaction_capability_skill_is_registered() -> None:
    entry = skill_runtime._entries.get("context.compaction.skill")
    assert entry is not None
    assert entry.skill_id == "context.compaction.skill"
