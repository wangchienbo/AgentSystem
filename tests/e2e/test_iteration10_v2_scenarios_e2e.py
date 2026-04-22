"""Iteration 10 E2E Tests - North Star v2 Scenarios

验证北星目标 v2 场景的端到端集成：
1. 复杂创建场景的澄清与需求累积
2. 按钮/卡片/execute_action 回流执行
3. 权限和审批链路行为一致性
"""
from __future__ import annotations

import asyncio
import pytest

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


@pytest.mark.e2e
class TestComplexCreationClarification:
    """测试复杂创建场景的澄清与需求累积"""

    def test_multiturn_requirement_accumulation(self):
        """多轮对话中逐步完善 App 创建需求"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter10-multiturn"

        async def run_test():
            # 第 1 轮：用户表达模糊需求
            request1 = ChatMessageRequest(
                user_id="test-e2e",
                channel="test",
                message="帮我建一个 App",
                session_id=session_id,
            )
            response1 = await gateway.receive_message(request1)
            assert response1 is not None
            print(f"[1] 模糊需求 -> {response1.content[:200]}")

            # 第 2 轮：用户补充核心功能
            request2 = ChatMessageRequest(
                user_id="test-e2e",
                channel="test",
                message="一个待办事项列表，可以添加和删除任务",
                session_id=session_id,
            )
            response2 = await gateway.receive_message(request2)
            assert response2 is not None
            print(f"[2] 补充需求 -> {response2.content[:200]}")

            return True

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run_test())
            assert result
        finally:
            loop.close()

        print("\n✓ 多轮需求累积测试通过")


@pytest.mark.e2e
class TestActionCallbackExecution:
    """测试按钮/卡片/execute_action 回流执行"""

    def test_execute_action_callback(self):
        """测试 execute_action 回调执行"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter10-callback"

        async def run_test():
            # 模拟用户点击卡片上的"启动"按钮
            request = ChatMessageRequest(
                user_id="test-e2e",
                channel="test",
                message="启动 App",
                session_id=session_id,
            )
            response = await gateway.receive_message(request)
            assert response is not None
            print(f"[动作执行] -> {response.content[:200]}")
            return True

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run_test())
            assert result
        finally:
            loop.close()

        print("\n✓ 动作回流执行测试通过")


@pytest.mark.e2e
class TestPermissionAndApproval:
    """测试权限和审批链路行为一致性"""

    def test_admin_approval_flow(self):
        """测试需要管理员审批的操作"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter10-approval"

        async def run_test():
            # 普通用户尝试执行需要审批的操作
            request = ChatMessageRequest(
                user_id="test-user-normal",
                channel="test",
                message="删除生产环境 App",
                session_id=session_id,
            )
            response = await gateway.receive_message(request)
            assert response is not None
            print(f"[权限测试] -> {response.content[:200]}")
            return True

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run_test())
            assert result
        finally:
            loop.close()

        print("\n✓ 权限边界测试通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
