import pytest

from app.services.requirement_blueprint_builder import (
    RequirementBlueprintBuilderError,
    RequirementBlueprintBuilderService,
)
from app.services.requirement_clarifier import RequirementClarifierService


clarifier = RequirementClarifierService()
builder = RequirementBlueprintBuilderService()


def test_builds_blueprint_draft_from_ready_app_requirement() -> None:
    spec = clarifier.clarify("帮我做一个客服审批系统 app，要能提交工单、分配处理人，并记录失败重试日志和权限边界")

    blueprint = builder.build_blueprint_draft(spec)

    assert blueprint.id.startswith("bp.requirement.")
    assert blueprint.goal == spec.goal
    assert len(blueprint.roles) >= 1
    assert len(blueprint.tasks) == 1
    assert len(blueprint.workflows) == 1
    assert blueprint.runtime_policy.execution_mode == "service"



def test_rejects_blueprint_draft_when_requirement_not_ready() -> None:
    spec = clarifier.clarify("这个流程有很多页面点击和表单操作，我先演示一遍，你再生成应用")

    with pytest.raises(RequirementBlueprintBuilderError):
        builder.build_blueprint_draft(spec)



def test_rejects_skill_only_requirement_for_app_blueprint_draft() -> None:
    spec = clarifier.clarify("写一个表单字段校验 skill，把输入统一转换成结构化 JSON，并检查缺失字段")

    with pytest.raises(RequirementBlueprintBuilderError):
        builder.build_blueprint_draft(spec)
