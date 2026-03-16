from app.models.experience import ExperienceRecord
from app.models.skill_blueprint import SkillBlueprint
from app.services.experience_store import ExperienceStore


def test_add_and_list_experiences() -> None:
    store = ExperienceStore()
    store.add_experience(
        ExperienceRecord(
            experience_id="exp.approval.001",
            title="审批经验",
            summary="请假流程需要主管审批后再通知人事。",
            source="document",
            tags=["approval", "hr"],
            related_skills=["skill.approval.route"],
        )
    )

    experiences = store.list_experiences()

    assert len(experiences) == 1
    assert experiences[0].experience_id == "exp.approval.001"


def test_link_experience_to_skill_blueprint() -> None:
    store = ExperienceStore()
    store.add_experience(
        ExperienceRecord(
            experience_id="exp.sync.001",
            title="文件同步经验",
            summary="冲突时优先保留最新版本并记录日志。",
            source="human_note",
        )
    )
    store.add_skill_blueprint(
        SkillBlueprint(
            skill_id="skill.file.sync.resolve",
            name="文件冲突处理",
            goal="处理文件同步冲突",
            inputs=["file_a", "file_b"],
            outputs=["resolved_file"],
            steps=["compare timestamp", "keep latest", "write audit log"],
            related_experience_ids=["exp.sync.001"],
        )
    )

    linked = store.suggest_skills_for_experience("exp.sync.001")

    assert len(linked) == 1
    assert linked[0].skill_id == "skill.file.sync.resolve"
