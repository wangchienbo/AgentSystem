from pathlib import Path

from app.bootstrap.runtime import build_runtime
from app.bootstrap.skills import bootstrap_builtin_skills
from app.models.skill_runtime import SkillExecutionRequest


APP_ID = "app.capability.demo"
WF_ID = "wf.capability.demo"
STEP_ID = "step.capability.demo"


def _build_services(tmp_path: Path) -> dict[str, object]:
    services = build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )
    bootstrap_builtin_skills(services["skill_runtime"], services)
    return services



def test_system_capability_skills_are_registered(tmp_path: Path) -> None:
    services = _build_services(tmp_path)
    skill_control = services["skill_control"]
    skill_ids = {item.skill_id for item in skill_control.list_skills()}
    assert "requirement.skill" in skill_ids
    assert "evidence.skill" in skill_ids
    assert "context.compaction.skill" in skill_ids


def test_requirement_capability_skill_executes(tmp_path: Path) -> None:
    services = _build_services(tmp_path)
    skill_runtime = services["skill_runtime"]
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



def test_evidence_capability_skill_executes(tmp_path: Path) -> None:
    services = _build_services(tmp_path)
    skill_runtime = services["skill_runtime"]
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



def test_context_compaction_capability_skill_is_registered(tmp_path: Path) -> None:
    services = _build_services(tmp_path)
    skill_runtime = services["skill_runtime"]
    entry = skill_runtime._entries.get("context.compaction.skill")
    assert entry is not None
    assert entry.skill_id == "context.compaction.skill"
