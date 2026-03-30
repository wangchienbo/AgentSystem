from app.services.requirement_router import RequirementRouter


router = RequirementRouter()


def test_routes_multi_constraint_app_request_without_forcing_demo() -> None:
    intent = router.route("帮我做一个客服审批系统 app，要能提交工单、分配处理人，并记录失败重试日志")

    assert intent.requirement_type == "app"
    assert intent.demonstration_decision == "optional"
    assert any(word in intent.extracted_keywords for word in ["app", "系统", "流程"])



def test_routes_ambiguous_tooling_request_to_hybrid_or_skill() -> None:
    intent = router.route("做一个数据清洗工具，最好既能当 skill 用，也能放进 workflow 里跑")

    assert intent.requirement_type in {"skill", "hybrid", "app"}
    assert intent.demonstration_decision in {"optional", "not_needed"}
    assert any(word in intent.extracted_keywords for word in ["workflow", "工具", "skill"])



def test_routes_demo_driven_ui_request_to_required_demonstration() -> None:
    intent = router.route("这个流程有很多页面点击和表单操作，我先演示一遍，你再生成应用")

    assert intent.requirement_type in {"app", "hybrid", "unclear"}
    assert intent.demonstration_decision == "required"
    assert any(word in intent.extracted_keywords for word in ["页面", "点击", "演示"])



def test_routes_abstract_strategy_request_to_clarify() -> None:
    intent = router.route("我想做一个长期的 AI 产品战略和架构规划，先帮我想方向")

    assert intent.requirement_type in {"unclear", "app", "hybrid"}
    assert intent.demonstration_decision == "clarify"
    assert any(word in intent.extracted_keywords for word in ["战略", "架构", "长期", "规划"])



def test_routes_skill_like_structured_request_without_clarification() -> None:
    intent = router.route("写一个表单字段校验 skill，把输入统一转换成结构化 JSON，并检查缺失字段")

    assert intent.requirement_type == "skill"
    assert intent.demonstration_decision == "not_needed"
    assert any(word in intent.extracted_keywords for word in ["skill", "校验", "转换"])
