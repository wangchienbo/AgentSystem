from app.services.requirement_router import RequirementRouter


def test_routes_app_request_with_optional_demonstration() -> None:
    router = RequirementRouter()

    intent = router.route("帮我做一个审批系统 app，用来提交和处理请假流程")

    assert intent.requirement_type == "app"
    assert intent.demonstration_decision == "optional"
    assert "系统" in intent.extracted_keywords


def test_routes_skill_request_without_demonstration() -> None:
    router = RequirementRouter()

    intent = router.route("写一个数据校验 skill，把表单输入转换成统一 JSON")

    assert intent.requirement_type == "skill"
    assert intent.demonstration_decision == "not_needed"
    assert "skill" in intent.extracted_keywords or "校验" in intent.extracted_keywords


def test_routes_demo_first_request() -> None:
    router = RequirementRouter()

    intent = router.route("我可以先示范一遍页面点击流程，你再帮我生成应用")

    assert intent.requirement_type in {"app", "unclear", "hybrid"}
    assert intent.demonstration_decision == "required"
    assert "示范" in intent.extracted_keywords or "点击" in intent.extracted_keywords


def test_routes_abstract_request_to_clarify() -> None:
    router = RequirementRouter()

    intent = router.route("我想规划一个长期 AI 战略架构")

    assert intent.demonstration_decision == "clarify"
    assert "战略" in intent.extracted_keywords or "架构" in intent.extracted_keywords
