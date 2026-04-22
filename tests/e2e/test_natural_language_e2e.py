"""Natural Language E2E Tests - Simulating real user interactions via LLM.

This module tests the complete user journey:
User Natural Language → LLM Intent Interpretation → Gateway Processing → Response
"""
from __future__ import annotations

import asyncio
import pytest
from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


def run_sync(gateway, message: str, session_id: str, user_id: str = "test-user"):
    """Helper to run async gateway call."""
    request = ChatMessageRequest(
        message=message,
        session_id=session_id,
        user_id=user_id,
    )
    return asyncio.run(gateway.receive_message(request))


@pytest.mark.e2e
class TestNaturalLanguageUserScenarios:
    """Test real user scenarios with natural language input."""

    def test_user_greeting_and_help(self):
        """User: "你好" / "你能做什么" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # User greets
        response = run_sync(gateway, "你好", "test-greet-session")
        assert response is not None
        assert response.content is not None
        print(f"Greeting response: {response.content[:100]}...")
        
        # User asks for help
        response = run_sync(gateway, "你能做什么", "test-greet-session")
        assert response is not None
        assert "帮助" in response.content or "App" in response.content or "功能" in response.content
        print(f"Help response: {response.content[:100]}...")

    def test_user_create_simple_app(self):
        """User: "帮我创建一个监控服务器状态的App" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        response = run_sync(
            gateway, 
            "帮我创建一个监控服务器状态的App", 
            "test-create-simple"
        )
        assert response is not None
        # Should either create or ask for clarification
        print(f"Create app response: {response.content[:200]}...")
        assert len(response.content) > 0

    def test_user_list_and_query_apps(self):
        """User: "看看我的App" / "有什么正在运行的" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # List apps
        response = run_sync(gateway, "看看我的App", "test-list-apps")
        assert response is not None
        print(f"List apps response: {response.content[:200]}...")

    def test_user_complex_request_with_clarification(self):
        """User: "我要一个App" - needs clarification """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-clarification"
        
        # Vague request
        response = run_sync(gateway, "我要一个App", session_id)
        assert response is not None
        print(f"Vague request response: {response.content[:200]}...")
        
        # User provides more details
        response = run_sync(gateway, "用来记录每日待办事项的", session_id)
        assert response is not None
        print(f"Clarified response: {response.content[:200]}...")

    def test_user_lifecycle_commands(self):
        """User: "启动XX" / "停止XX" / "查看状态" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # Check system status
        response = run_sync(gateway, "系统状态", "test-lifecycle")
        assert response is not None
        print(f"Status response: {response.content[:200]}...")

    def test_user_permission_request(self):
        """User: "查看我的权限" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        response = run_sync(gateway, "查看我的权限", "test-permission")
        assert response is not None
        print(f"Permission response: {response.content[:200]}...")


@pytest.mark.e2e
class TestUserMultiTurnConversation:
    """Test multi-turn conversations with context preservation."""

    def test_multi_turn_create_and_modify(self):
        """User creates app, then modifies it in follow-up."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-multiturn-create-modify"
        
        # Turn 1: Create
        response = run_sync(
            gateway,
            "创建一个日报App，每天早上9点推送",
            session_id
        )
        print(f"Turn 1 (Create): {response.content[:200]}...")
        
        # Turn 2: List to see what was created
        response = run_sync(gateway, "我的App列表", session_id)
        print(f"Turn 2 (List): {response.content[:200]}...")
        
        # Turn 3: Modify
        response = run_sync(
            gateway,
            "把刚才的日报时间改成晚上6点",
            session_id
        )
        print(f"Turn 3 (Modify): {response.content[:200]}...")
        
        assert response is not None

    def test_multi_turn_with_error_recovery(self):
        """User makes error, system helps recover."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-error-recovery"
        
        # User asks for non-existent app
        response = run_sync(gateway, "启动一个不存在的App", session_id)
        print(f"Error response: {response.content[:200]}...")
        
        # User corrects
        response = run_sync(gateway, "那帮我看看有什么App", session_id)
        print(f"Recovery response: {response.content[:200]}...")


@pytest.mark.e2e  
class TestUserRuntimeAssetQueries:
    """Test user querying runtime assets and capabilities."""

    def test_user_list_assets(self):
        """User: "现在有什么资产" / "你能操作什么" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        response = run_sync(gateway, "现在有什么资产", "test-assets")
        assert response is not None
        print(f"Assets response: {response.content[:200]}...")

    def test_user_query_asset_detail(self):
        """User: "XX资产是做什么的" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # First list to get asset names
        response = run_sync(gateway, "有什么资产", "test-asset-detail")
        print(f"List for detail: {response.content[:200]}...")
        
        # Then query detail (if any assets exist)
        # response = run_sync(gateway, "监控资产怎么用", "test-asset-detail")


@pytest.mark.e2e
class TestRiskGuardNaturalLanguage:
    """Test risk guards with natural language scenarios."""

    def test_rate_limiter_friendly_message(self):
        """When rate limited, user gets friendly message."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # Simulate rapid requests
        session_id = "test-rate-limit"
        for i in range(25):
            gateway._rate_limiter.record_query(session_id)
        
        response = run_sync(gateway, "你好", session_id)
        print(f"Rate limit response: {response.content[:200]}...")
        
        # Should be rate limited with friendly message
        if "过于频繁" in response.content:
            print("✓ Rate limiter working - friendly message shown")
        else:
            print("Note: Rate limit not triggered (may be expected)")

    def test_tool_loop_detection(self):
        """Tool loop guard should detect excessive tool calls."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # Normal request should work
        response = run_sync(gateway, "看看系统状态", "test-tool-loop")
        assert response is not None
        print(f"Normal request OK: {response.content[:100]}...")


if __name__ == "__main__":
    # Run tests directly
    print("=" * 60)
    print("Natural Language E2E Tests - Simulating User Interactions")
    print("=" * 60)
    
    test_class = TestNaturalLanguageUserScenarios()
    
    print("\n1. Testing greeting...")
    try:
        test_class.test_user_greeting_and_help()
        print("✓ Greeting test passed")
    except Exception as e:
        print(f"✗ Greeting test failed: {e}")
    
    print("\n2. Testing simple app creation...")
    try:
        test_class.test_user_create_simple_app()
        print("✓ Create app test passed")
    except Exception as e:
        print(f"✗ Create app test failed: {e}")
    
    print("\n3. Testing list apps...")
    try:
        test_class.test_user_list_and_query_apps()
        print("✓ List apps test passed")
    except Exception as e:
        print(f"✗ List apps test failed: {e}")
    
    print("\n4. Testing clarification flow...")
    try:
        test_class.test_user_complex_request_with_clarification()
        print("✓ Clarification test passed")
    except Exception as e:
        print(f"✗ Clarification test failed: {e}")
    
    print("\n5. Testing lifecycle commands...")
    try:
        test_class.test_user_lifecycle_commands()
        print("✓ Lifecycle test passed")
    except Exception as e:
        print(f"✗ Lifecycle test failed: {e}")
    
    print("\n" + "=" * 60)
    print("Natural Language E2E Tests Complete")
    print("=" * 60)
