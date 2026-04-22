"""Extended Natural Language E2E Tests - Multi-scenario user interactions.

Tests cover the complete user journey with various real-world scenarios.
All tests run against the actual installed system in /root/project/AgentSystem
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
class TestExtendedUserScenarios:
    """Extended real user scenarios with natural language input."""

    def test_user_greeting_variations(self):
        """Test various greeting patterns."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        greetings = ["你好", "hello", "hi", "早上好", "晚上好"]
        for greeting in greetings:
            response = run_sync(gateway, greeting, f"test-greet-{greeting}")
            assert response is not None
            assert response.content is not None
            print(f"✓ Greeting '{greeting}': {response.content[:50]}...")

    def test_help_and_capability_queries(self):
        """Test various help and capability questions."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        queries = [
            "你能做什么",
            "有什么功能",
            "如何使用",
            "帮我介绍下",
        ]
        for query in queries:
            response = run_sync(gateway, query, f"test-help-{query}")
            assert response is not None
            assert response.content is not None
            print(f"✓ Help '{query}': {response.content[:50]}...")

    def test_app_creation_patterns(self):
        """Test various app creation requests."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        requests = [
            ("创建一个待办 App", "test-create-todo"),
            ("帮我做个监控服务器状态的 App", "test-create-monitor"),
            ("我需要一个日记 App", "test-create-diary"),
        ]
        for request, session in requests:
            response = run_sync(gateway, request, session)
            assert response is not None
            print(f"✓ Create '{request}': {response.content[:100]}...")

    def test_app_lifecycle_queries(self):
        """Test app lifecycle management queries."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        queries = [
            "我的 App 有哪些",
            "看看有什么 App",
            "系统状态",
            "有什么正在运行",
        ]
        for i, query in enumerate(queries):
            session = f"test-lifecycle-{i}"
            response = run_sync(gateway, query, session)
            assert response is not None
            print(f"✓ Lifecycle '{query}': {response.content[:100]}...")

    def test_asset_queries(self):
        """Test runtime asset queries."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        queries = [
            "现在有什么资产",
            "你能操作什么",
            "支持哪些工具",
        ]
        for query in queries:
            response = run_sync(gateway, query, "test-assets")
            assert response is not None
            print(f"✓ Assets '{query}': {response.content[:100]}...")

    def test_error_handling(self):
        """Test error handling with invalid requests."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        # Test with unclear requests (empty string not allowed by validation)
        responses = [
            run_sync(gateway, "????", "test-error-chars"),
            run_sync(gateway, "...", "test-error-dots"),
        ]
        
        for response in responses:
            assert response is not None
            # System should respond gracefully even to invalid input
            print(f"✓ Error handling: {response.content[:100]}...")

    def test_multi_turn_context(self):
        """Test context preservation across turns."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "test-context"
        
        # Turn 1: Greeting
        response = run_sync(gateway, "你好", session)
        assert response is not None
        print(f"Turn 1: {response.content[:50]}...")
        
        # Turn 2: Follow-up
        response = run_sync(gateway, "你能做什么", session)
        assert response is not None
        print(f"Turn 2: {response.content[:50]}...")
        
        # Turn 3: More specific
        response = run_sync(gateway, "帮我创建一个 App", session)
        assert response is not None
        print(f"Turn 3: {response.content[:100]}...")


@pytest.mark.e2e
class TestSystemIntegration:
    """Test system integration points."""

    def test_runtime_build(self):
        """Test that runtime builds correctly."""
        services = build_runtime()
        
        assert "light_brain_gateway" in services
        assert "runtime_center" in services
        print("✓ Runtime build successful")

    def test_gateway_initialization(self):
        """Test gateway initializes correctly."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        assert gateway is not None
        assert hasattr(gateway, "receive_message")
        print("✓ Gateway initialization successful")

    def test_concurrent_sessions(self):
        """Test multiple concurrent sessions."""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        
        sessions = ["session-1", "session-2", "session-3"]
        for session in sessions:
            response = run_sync(gateway, "你好", session)
            assert response is not None
            print(f"✓ Session {session}: OK")


if __name__ == "__main__":
    print("=" * 60)
    print("Extended Natural Language E2E Tests")
    print("=" * 60)
    
    test_class = TestExtendedUserScenarios()
    
    tests = [
        ("Greetings", test_class.test_user_greeting_variations),
        ("Help Queries", test_class.test_help_and_capability_queries),
        ("App Creation", test_class.test_app_creation_patterns),
        ("Lifecycle", test_class.test_app_lifecycle_queries),
        ("Asset Queries", test_class.test_asset_queries),
        ("Error Handling", test_class.test_error_handling),
        ("Multi-turn Context", test_class.test_multi_turn_context),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            print(f"\n{name}...")
            test_func()
            passed += 1
            print(f"✓ {name} passed")
        except Exception as e:
            failed += 1
            print(f"✗ {name} failed: {e}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
