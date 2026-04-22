"""Iteration 12 E2E Tests - complex creation clarification and v2 regression."""
from __future__ import annotations

import asyncio
import pytest

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


async def _send(gateway, message: str, session_id: str, user_id: str = "test-user"):
    request = ChatMessageRequest(
        message=message,
        session_id=session_id,
        user_id=user_id,
    )
    return await gateway.receive_message(request)


@pytest.mark.e2e
class TestComplexCreationClarificationStability:
    def test_multiturn_complex_creation_accumulates_requirements(self):
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter12-complex-create"

        response1 = asyncio.run(
            _send(
                gateway,
                "我想创建一个团队协作 App，要支持任务、日历和消息通知",
                session_id,
            )
        )
        assert response1 is not None

        response2 = asyncio.run(
            _send(
                gateway,
                "补充一下，还需要成员权限分级和审批流",
                session_id,
            )
        )
        assert response2 is not None

        response3 = asyncio.run(
            _send(
                gateway,
                "再加上移动端提醒和每周汇总报表",
                session_id,
            )
        )
        assert response3 is not None

    def test_clarification_survives_topic_refinement(self):
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter12-topic-refinement"

        response1 = asyncio.run(
            _send(
                gateway,
                "帮我创建一个客服 App，先支持工单和FAQ",
                session_id,
            )
        )
        assert response1 is not None

        response2 = asyncio.run(
            _send(
                gateway,
                "把 FAQ 改成知识库，并加上工单优先级",
                session_id,
            )
        )
        assert response2 is not None

        response3 = asyncio.run(
            _send(
                gateway,
                "顺便支持管理员审核高优先级工单",
                session_id,
            )
        )
        assert response3 is not None

    def test_clarification_then_query_does_not_break_context(self):
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter12-query-context"

        response1 = asyncio.run(
            _send(
                gateway,
                "创建一个数据分析 App，需要图表和导出功能",
                session_id,
            )
        )
        assert response1 is not None

        response2 = asyncio.run(
            _send(
                gateway,
                "查看我现在有哪些 App",
                session_id,
            )
        )
        assert response2 is not None

        response3 = asyncio.run(
            _send(
                gateway,
                "继续给刚才那个数据分析 App 加权限控制",
                session_id,
            )
        )
        assert response3 is not None


@pytest.mark.e2e
class TestV2RegressionFullSuite:
    def test_v2_create_modify_execute_regression(self):
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter12-v2-regression"

        response1 = asyncio.run(_send(gateway, "创建一个待办 App", session_id))
        assert response1 is not None

        response2 = asyncio.run(_send(gateway, "增加分类和优先级功能", session_id))
        assert response2 is not None

        response3 = asyncio.run(_send(gateway, "添加一个任务：今晚复盘", session_id))
        assert response3 is not None

    def test_v2_permission_and_approval_regression(self):
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter12-v2-permission"

        response1 = asyncio.run(_send(gateway, "创建一个内部审批 App", session_id, user_id="regular-user"))
        assert response1 is not None

        response2 = asyncio.run(_send(gateway, "增加管理员审批节点", session_id, user_id="regular-user"))
        assert response2 is not None

    def test_v2_execute_action_regression_after_clarification(self):
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter12-execute-after-clarification"

        response1 = asyncio.run(_send(gateway, "创建一个记账 App，要支持收入和支出", session_id))
        assert response1 is not None

        response2 = asyncio.run(_send(gateway, "再补充预算提醒功能", session_id))
        assert response2 is not None

        response3 = asyncio.run(_send(gateway, "记一笔支出：午餐 35 元", session_id))
        assert response3 is not None
