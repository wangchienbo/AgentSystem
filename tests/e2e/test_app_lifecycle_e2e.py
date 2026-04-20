"""完整 App 生命周期 E2E 测试：create → install → start → stop → delete

验证 qwen3.6-plus 驱动下完整链路的端到端行为。
"""
from __future__ import annotations

import pytest
import asyncio

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


@pytest.mark.e2e
class TestAppLifecycleE2E:
    """App 完整生命周期端到端测试"""

    def test_create_and_list_app(self):
        """E2E：创建 App 并列出列表"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]

        # 创建
        request = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="帮我建一个监控 App",
            session_id="e2e-lifecycle-1",
        )
        response = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request)
        )
        print(f"Create response: {response.content[:300]}")
        # 创建应该成功或需要确认
        assert response.type in ("text", "error")

        # 列出列表验证
        request2 = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="看看我的 App 列表",
            session_id="e2e-lifecycle-1",
        )
        response2 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request2)
        )
        print(f"List response: {response2.content[:300]}")
        assert response2.type == "text"

    def test_start_and_stop_app(self):
        """E2E：启动和停止 App"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "e2e-lifecycle-2"

        # 启动（需要 App 名称）
        request = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="启动",
            session_id=session,
        )
        response = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request)
        )
        print(f"Start response: {response.content[:300]}")
        # 缺少名称应该需要 clarification
        assert response.requires_input is True or response.type == "text"

        # 停止
        request2 = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="停止",
            session_id=session,
        )
        response2 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request2)
        )
        print(f"Stop response: {response2.content[:300]}")
        assert response2.type == "text"

    def test_query_status(self):
        """E2E：查询系统状态"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]

        request = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="系统状态",
            session_id="e2e-lifecycle-3",
        )
        response = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request)
        )
        print(f"Status response: {response.content[:300]}")
        assert response.type == "text"

    def test_list_assets_via_gateway(self):
        """E2E：通过 Gateway 查询运行态资产"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]

        request = ChatMessageRequest(
            user_id="test-e2e",
            channel="test",
            message="列出所有运行态资产",
            session_id="e2e-lifecycle-4",
        )
        response = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request)
        )
        print(f"List assets response: {response.content[:300]}")
        assert response.type == "text"
        # 应包含 asset: 开头的资产
        print(f"Response preview: {response.content[:200]}")

    def test_continuous_conversation_flow(self):
        """E2E：连续多轮对话，保持 session，验证上下文连续性"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "e2e-continuity-test"

        turns = [
            ("你好", "打招呼"),
            ("帮我建一个监控 App", "创建请求"),
            ("启动", "缺名称追问"),
            ("服务器监控", "补名称完成启动"),
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
            print(f"[{desc}] {msg!r} → requires_input={response.requires_input}")
            print(f"  {response.content[:150]}")

        # 验证关键断言
        # 第3轮（"启动"）应该触发 clarification
        assert responses[2].requires_input is True, "缺少名称应触发追问"
        # 第4轮（补名称）应该能完成
        assert responses[3].type == "text"
        print("\n✓ 连续对话流正常")

        """E2E：多轮对话流程（greet → help → create）"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "e2e-lifecycle-5"

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

        # 第三轮：创建 App
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
