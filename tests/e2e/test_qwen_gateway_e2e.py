"""端到端测试：Gateway + qwen3.6-plus + runtime asset clarification 链路

验证配置切换后整个链路仍能正常工作。
"""
from __future__ import annotations

import pytest
import re
import asyncio

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


@pytest.mark.e2e
class TestQwenGatewayE2E:
    """端到端测试类"""

    def test_e2e_runtime_asset_detail(self):
        """端到端：查看资产详情"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        request = ChatMessageRequest(
            user_id="test-user",
            channel="test",
            message="查看资产 asset:runtime_center:v1 的详情",
            session_id="e2e-test-detail",
        )
        
        response = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request)
        )
        
        print(f"Response type: {response.type}")
        print(f"Content preview: {response.content[:200]}...")
        assert response.type == "text"
        assert "asset:runtime_center:v1" in response.content

    def test_e2e_runtime_asset_call_with_clarification(self):
        """端到端：调用资产方法，需要 clarification"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # 第一轮：触发 clarification
        request1 = ChatMessageRequest(
            user_id="test-user",
            channel="test",
            message="调用资产 asset:runtime_center:v1 的方法",
            session_id="e2e-test-clarify",
        )
        
        response1 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request1)
        )
        
        print(f"Round 1 - requires_input: {response1.requires_input}")
        print(f"Clarification question: {response1.content[:150]}...")
        assert response1.requires_input is True
        assert "方法" in response1.content or "method" in response1.content.lower()
        
        # 第二轮：补充方法名
        request2 = ChatMessageRequest(
            user_id="test-user",
            channel="test",
            message="list_assets",
            session_id="e2e-test-clarify",
        )
        
        response2 = asyncio.get_event_loop().run_until_complete(
            gateway.receive_message(request2)
        )
        
        print(f"Round 2 - requires_input: {response2.requires_input}")
        print(f"Response preview: {response2.content[:200]}...")
        assert response2.requires_input is False
        assert "asset:runtime_center:v1" in response2.content
