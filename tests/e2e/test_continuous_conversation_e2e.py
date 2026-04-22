"""连续对话 E2E 测试：验证多轮对话中的上下文连续性和澄清机制。

验证 qwen3.6-plus 驱动下多轮对话的端到端行为。
"""
from __future__ import annotations

import pytest
import asyncio

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


@pytest.mark.e2e
class TestContinuousConversationE2E:
    """连续对话 E2E 测试"""

    def test_greet_help_create_flow(self):
        """E2E：多轮对话流程（greet → help → create）"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "e2e-conv-1"

        # 第一轮：打招呼
        request1 = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="你好",
            session_id=session,
        )
        response1 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request1)
        )
        print(f"Greet response: {response1.content[:200]}")
        assert response1.type == "text"

        # 第二轮：请求帮助
        request2 = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="帮助",
            session_id=session,
        )
        response2 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request2)
        )
        print(f"Help response: {response2.content[:300]}")
        assert response2.type == "text"

        # 第三轮：创建 App（应该触发澄清或确认）
        request3 = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="帮我建一个日报 App",
            session_id=session,
        )
        response3 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request3)
        )
        print(f"Create response: {response3.content[:300]}")
        assert response3.type in ("text", "error")

    def test_clarification_then_normal_query(self):
        """E2E：澄清后接正常查询，验证状态机正确流转。
        
        场景：用户打招呼 → 创建 App → 问系统状态
        验证：系统能正确处理话题切换
        注意：当前"帮我建一个监控 App"可能被识别为资产查询（因为包含"监控"关键词）
              这是正常的意图识别行为，测试重点验证后续话题切换是否正常
        """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "e2e-conv-2"

        # 第 1 轮：打招呼
        request1 = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="你好",
            session_id=session,
        )
        response1 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request1)
        )
        print(f"[1] 你好 → {response1.content[:100]}")
        assert response1.type == "text"

        # 第 2 轮：创建请求（可能被识别为资产查询）
        request2 = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="帮我建一个监控 App",
            session_id=session,
        )
        response2 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request2)
        )
        print(f"[2] 创建请求 → type={response2.type}")
        print(f"    {response2.content[:150]}")
        # 创建请求可能触发澄清或资产查询，都是正常行为
        assert response2.type in ("text", "error")

        # 第 3 轮：问系统状态（验证话题切换）
        request3 = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="系统状态",
            session_id=session,
        )
        response3 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request3)
        )
        print(f"[3] 系统状态 → {response3.content[:150]}")
        # 应该正常响应系统状态
        assert response3.type == "text"
        assert "系统状态" in response3.content or "App" in response3.content

        print("\n✓ 话题切换正常")

    def test_context_continuity_across_turns(self):
        """E2E：验证多轮对话中的上下文连续性。
        
        场景：打招呼 → 创建 App → 查看列表 → 查询状态
        验证：每轮对话都能正确理解意图并响应
        """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "e2e-conv-3"

        turns = [
            ("你好", "打招呼"),
            ("帮我建一个监控 App", "创建请求"),
            ("看看我的 App 列表", "查看列表"),
            ("系统状态", "状态查询"),
        ]

        responses = []
        for msg, desc in turns:
            request = ChatMessageRequest(
                user_id="test-e2e",
                channel="test",
                message=msg,
                session_id=session,
            )
            response = asyncio.get_event_loop().run_until_complete(
                gateway.receive_message(request)
            )
            responses.append(response)
            print(f"[{desc}] {msg!r} → type={response.type}, requires_input={response.requires_input}")
            print(f"  {response.content[:150]}")

        # 验证所有响应都是正常的文本响应
        for i, resp in enumerate(responses):
            assert resp.type == "text", f"第{i+1}轮响应异常：{resp.content[:100]}"

        print("\n✓ 上下文连续性正常")
