from app.services.requirement_clarifier import RequirementClarifierService


service = RequirementClarifierService()


def test_clarifier_marks_abstract_request_as_needing_clarification() -> None:
    spec = service.clarify("我想做一个长期 AI 战略架构规划")

    assert spec.readiness == "needs_clarification"
    assert "artifact_type" in spec.missing_fields or "outputs" in spec.missing_fields
    assert len(spec.recommended_questions) >= 1



def test_clarifier_marks_ui_demo_request_as_needing_demo() -> None:
    spec = service.clarify("这个流程有很多页面点击和表单操作，我先演示一遍，你再生成应用")

    assert spec.needs_demo is True
    assert spec.readiness == "needs_demo"
    assert any("演示" in item or "页面" in item for item in spec.extracted_keywords)
    assert any("演示" in question for question in spec.recommended_questions)



def test_clarifier_extracts_structured_skill_signals() -> None:
    spec = service.clarify("写一个表单字段校验 skill，把输入统一转换成结构化 JSON，并检查缺失字段")

    assert spec.requirement_type == "skill"
    assert spec.readiness == "ready"
    assert "user_input" in spec.inputs
    assert "structured_output" in spec.outputs
    assert spec.failure_strategy is None



def test_clarifier_extracts_app_constraints_and_failure_strategy() -> None:
    spec = service.clarify("帮我做一个客服审批系统 app，要能提交工单、分配处理人，并记录失败重试日志和权限边界")

    assert spec.requirement_type == "app"
    assert spec.failure_strategy == "retry_on_failure"
    assert "approval_flow" in spec.permissions
    assert any(item in spec.constraints for item in ["失败重试", "权限", "审批"])
    assert spec.readiness == "ready"



def test_readiness_endpoint_shape_is_minimal_and_actionable() -> None:
    result = service.readiness("做一个数据清洗工具")

    assert "readiness" in result
    assert "missing_fields" in result
    assert "recommended_questions" in result
    assert result["requirement_type"] in {"skill", "hybrid", "app", "unclear"}
