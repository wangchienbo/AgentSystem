from app.models.demonstration import DemonstrationRecord
from app.services.demonstration_extractor import DemonstrationExtractor


def test_extract_demonstration_into_experience_and_skill() -> None:
    extractor = DemonstrationExtractor()
    record = DemonstrationRecord(
        demonstration_id="approval.flow.001",
        title="请假审批演示",
        goal="从提交申请到主管审批完成",
        steps=[
            "打开审批页面",
            "填写请假表单",
            "提交给主管",
            "主管点击通过",
        ],
        observed_inputs=["leave_form"],
        observed_outputs=["approved_request"],
    )

    experience, skill = extractor.extract(record)

    assert experience.source == "demonstration"
    assert experience.experience_id == "exp.approval.flow.001"
    assert skill.skill_id == "skill.approval.flow.001"
    assert skill.related_experience_ids == ["exp.approval.flow.001"]
    assert "填写请假表单" in skill.steps
