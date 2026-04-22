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
        assert response.content is not None
        print(f"Help response: {response.content[:100]}...")

    def test_user_create_simple_app(self):
        """User: "帮我创建一个监控服务器状态的 App" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        response = run_sync(
            gateway, 
            "帮我创建一个监控服务器状态的 App", 
            "test-create-simple"
        )
        assert response is not None
        # Should either create or ask for clarification
        print(f"Create app response: {response.content[:200]}...")

    def test_user_list_and_query_apps(self):
        """User: "看看我的 App" / "有什么正在运行的" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # List apps
        response = run_sync(gateway, "看看我的 App", "test-list-apps")
        assert response is not None
        print(f"List apps response: {response.content[:200]}...")

    def test_user_lifecycle_commands(self):
        """User: "启动 XX" / "停止 XX" / "查看状态" """
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # Check system status
        response = run_sync(gateway, "系统状态", "test-lifecycle")
        assert response is not None
        print(f"Status response: {response.content[:200]}...")


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
    
    print("\n4. Testing lifecycle commands...")
    try:
        test_class.test_user_lifecycle_commands()
        print("✓ Lifecycle test passed")
    except Exception as e:
        print(f"✗ Lifecycle test failed: {e}")
    
    print("\n" + "=" * 60)
    print("Natural Language E2E Tests Complete")
    print("=" * 60)
