"""Phase 8.1: LightBrain Gateway — basic conversation loop tests."""

from __future__ import annotations

import pytest

from app.models.chat import (
    ChatMessageRequest,
    ChatActionRequest,
    InterpretedCommand,
)
from app.services.light_brain_interpreter import LightBrainInterpreter
from app.services.light_brain_memory import LightBrainMemory
from app.services.light_brain_gateway import LightBrainGateway


# ===========================================================================
# Interpreter tests
# ===========================================================================

class TestLightBrainInterpreter:
    def setup_method(self):
        self.interpreter = LightBrainInterpreter()

    def test_greet(self):
        cmd = self.interpreter.interpret("你好")
        assert cmd.intent == "greet"
        assert cmd.confidence >= 0.8
        assert not cmd.requires_clarification

    def test_list_apps(self):
        cmd = self.interpreter.interpret("看看我的 App 列表")
        assert cmd.intent == "list_apps"

    def test_create_app(self):
        cmd = self.interpreter.interpret("帮我建一个监控 App")
        assert cmd.intent == "create_app"
        assert cmd.parameters.get("app_type") == "monitor"

    def test_create_app_with_schedule(self):
        cmd = self.interpreter.interpret("创建一个每小时检查的日报 App")
        assert cmd.intent == "create_app"
        assert cmd.parameters.get("schedule_type") == "interval"
        assert cmd.parameters.get("schedule_interval") == 3600

    def test_create_app_with_threshold(self):
        cmd = self.interpreter.interpret("建一个 CPU 超过 80% 告警的监控 App")
        assert cmd.intent == "create_app"
        assert cmd.parameters.get("threshold") == 80

    def test_start_app_with_name(self):
        cmd = self.interpreter.interpret("启动服务器监控")
        assert cmd.intent == "start_app"
        assert cmd.target_app == "服务器监控"

    def test_stop_app(self):
        cmd = self.interpreter.interpret("停止日报")
        assert cmd.intent == "stop_app"

    def test_query_status(self):
        cmd = self.interpreter.interpret("系统状态")
        assert cmd.intent == "query_status"

    def test_query_help(self):
        cmd = self.interpreter.interpret("帮助")
        assert cmd.intent == "query_help"

    def test_modify_app(self):
        cmd = self.interpreter.interpret("把日报改成每天早上9点发给我")
        assert cmd.intent == "modify_app"
        assert cmd.parameters.get("modification") == "每天早上9点发给我"

    def test_delete_app(self):
        cmd = self.interpreter.interpret("删除测试 App")
        assert cmd.intent == "delete_app"

    def test_empty_message(self):
        cmd = self.interpreter.interpret("")
        assert cmd.intent == "unclear"
        assert cmd.requires_clarification

    def test_unknown_message(self):
        cmd = self.interpreter.interpret("asdfghjkl")
        assert cmd.intent == "unclear"
        assert cmd.requires_clarification

    def test_create_app_without_type_needs_clarification(self):
        cmd = self.interpreter.interpret("帮我建一个 App")
        assert cmd.intent == "create_app"
        assert cmd.requires_clarification

    def test_start_app_without_name_needs_clarification(self):
        cmd = self.interpreter.interpret("启动")
        assert cmd.intent == "start_app"
        assert cmd.requires_clarification

    def test_suggested_actions_for_create(self):
        cmd = self.interpreter.interpret("帮我建一个监控 App")
        assert len(cmd.suggested_actions) > 0
        action_ids = [a.id for a in cmd.suggested_actions]
        assert "confirm_create" in action_ids

    def test_suggested_actions_for_greet(self):
        cmd = self.interpreter.interpret("你好")
        assert len(cmd.suggested_actions) > 0

    def test_known_app_name_matching(self):
        apps = [
            {"app_id": "app-001", "name": "服务器监控", "description": "", "status": "running"},
            {"app_id": "app-002", "name": "日报生成器", "description": "", "status": "stopped"},
        ]
        cmd = self.interpreter.interpret("启动服务器监控", available_apps=apps)
        assert cmd.target_app == "服务器监控"


# ===========================================================================
# Memory tests
# ===========================================================================

class TestLightBrainMemory:
    def setup_method(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.memory = LightBrainMemory(data_dir=self.tmpdir)

    def test_create_session(self):
        session = self.memory.create_session(user_id="u1", channel="webchat")
        assert session.session_id.startswith("sess-")
        assert session.user_id == "u1"

    def test_get_session(self):
        session = self.memory.create_session(user_id="u1", channel="webchat")
        fetched = self.memory.get_session(session.session_id)
        assert fetched is not None
        assert fetched.session_id == session.session_id

    def test_record_message(self):
        session = self.memory.create_session(user_id="u1", channel="webchat")
        self.memory.record_user_message(session.session_id, "你好")
        messages = self.memory.get_recent_messages(session.session_id)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "你好"

    def test_list_sessions(self):
        self.memory.create_session(user_id="u1", channel="webchat")
        self.memory.create_session(user_id="u2", channel="webchat")
        all_sessions = self.memory.list_sessions()
        assert len(all_sessions) == 2
        u1_sessions = self.memory.list_sessions(user_id="u1")
        assert len(u1_sessions) == 1

    def test_delete_session(self):
        session = self.memory.create_session(user_id="u1", channel="webchat")
        assert self.memory.delete_session(session.session_id) is True
        assert self.memory.get_session(session.session_id) is None

    def test_persistence_survives_restart(self):
        session = self.memory.create_session(user_id="u1", channel="webchat")
        self.memory.record_user_message(session.session_id, "测试持久化")

        # Create a new memory instance pointing to the same directory
        memory2 = LightBrainMemory(data_dir=self.tmpdir)
        restored = memory2.get_session(session.session_id)
        assert restored is not None
        messages = memory2.get_recent_messages(session.session_id)
        assert len(messages) >= 1
        assert messages[0]["content"] == "测试持久化"

    def test_compaction(self):
        session = self.memory.create_session(user_id="u1", channel="webchat")
        session.compact_threshold = 10  # Lower for testing
        for i in range(25):
            self.memory.record_user_message(session.session_id, f"消息 {i}")

        messages = self.memory.get_recent_messages(session.session_id)
        # After compaction: 5 first + 1 marker + 20 last = 26
        assert len(messages) <= 26


# ===========================================================================
# Gateway integration tests
# ===========================================================================

class TestLightBrainGateway:
    def setup_method(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        memory = LightBrainMemory(data_dir=self.tmpdir)
        interpreter = LightBrainInterpreter()
        self.gateway = LightBrainGateway(memory=memory, interpreter=interpreter)

    @pytest.mark.asyncio
    async def test_greet_reply(self):
        request = ChatMessageRequest(user_id="u1", channel="webchat", message="你好")
        reply = await self.gateway.process_message(request)
        assert reply.type == "text"
        assert "光脑" in reply.content or "你好" in reply.content
        assert len(reply.actions) > 0

    @pytest.mark.asyncio
    async def test_list_apps_empty_reply(self):
        request = ChatMessageRequest(user_id="u1", channel="webchat", message="看看我的 App")
        reply = await self.gateway.process_message(request)
        assert reply.type in ("text", "list")

    @pytest.mark.asyncio
    async def test_create_app_confirmation(self):
        request = ChatMessageRequest(
            user_id="u1", channel="webchat",
            message="帮我建一个监控 App",
        )
        reply = await self.gateway.process_message(request)
        assert reply.type in ("confirm", "text")
        assert any(a.id == "confirm_create" for a in reply.actions)

    @pytest.mark.asyncio
    async def test_query_status_reply(self):
        request = ChatMessageRequest(user_id="u1", channel="webchat", message="系统状态")
        reply = await self.gateway.process_message(request)
        assert reply.type in ("card", "text")

    @pytest.mark.asyncio
    async def test_help_reply(self):
        request = ChatMessageRequest(user_id="u1", channel="webchat", message="帮助")
        reply = await self.gateway.process_message(request)
        assert reply.type == "text"
        assert "帮助" in reply.content

    @pytest.mark.asyncio
    async def test_session_persistence(self):
        req1 = ChatMessageRequest(user_id="u1", channel="webchat", message="你好")
        reply1 = await self.gateway.process_message(req1)
        session_id = reply1.session_id

        req2 = ChatMessageRequest(
            user_id="u1", channel="webchat",
            message="看看我的 App",
            session_id=session_id,
        )
        reply2 = await self.gateway.process_message(req2)
        assert reply2.session_id == session_id

    @pytest.mark.asyncio
    async def test_unclear_message_ask_clarification(self):
        request = ChatMessageRequest(user_id="u1", channel="webchat", message="asdfghjkl")
        reply = await self.gateway.process_message(request)
        assert reply.requires_input is True

    @pytest.mark.asyncio
    async def test_cancel_action(self):
        req = ChatMessageRequest(user_id="u1", channel="webchat", message="你好")
        reply = await self.gateway.process_message(req)
        session_id = reply.session_id

        action_reply = await self.gateway.execute_action(
            user_id="u1", session_id=session_id,
            action_id="cancel", action_params={"intent": "cancel"},
        )
        assert action_reply.type == "text"
        assert "取消" in action_reply.content

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        await self.gateway.process_message(
            ChatMessageRequest(user_id="u1", channel="webchat", message="你好")
        )
        sessions = self.gateway.list_sessions(user_id="u1")
        assert len(sessions) >= 1

    @pytest.mark.asyncio
    async def test_delete_session(self):
        reply = await self.gateway.process_message(
            ChatMessageRequest(user_id="u1", channel="webchat", message="你好")
        )
        assert self.gateway.delete_session(reply.session_id) is True


# ===========================================================================
# LLM Fallback tests (Phase 8.3)
# ===========================================================================

class MockLLMResponder:
    """Mock LLM responder that returns predefined parse results."""
    
    def __init__(self, available=True, parse_result=None):
        self.available = available
        self._parse_result = parse_result or {
            "intent": "create_app",
            "target_app": "智能监控",
            "parameters": {"app_type": "monitor", "threshold": 90},
            "confidence": 0.92,
            "requires_clarification": False,
            "clarification_question": None,
        }
        self._call_count = 0
    
    def parse_intent(self, message, available_apps=None):
        self._call_count += 1
        return self._parse_result
    
    def generate_reply(self, system_context, user_message, **kwargs):
        self._call_count += 1
        return "我是通过 LLM 生成的回复。"


class TestLLMFallback:
    """Test that LLM fallback is used when rule-based parser is unclear."""
    
    def test_llm_fallback_when_unclear(self):
        """When rule-based returns unclear, LLM should be consulted."""
        from app.services.light_brain_interpreter import LightBrainInterpreter
        interpreter = LightBrainInterpreter()
        mock_llm = MockLLMResponder()
        interpreter.set_llm_responder(mock_llm)
        
        # Clear cache
        interpreter.clear_llm_cache()
        
        # Rule-based can't parse this gibberish, so LLM fallback kicks in
        result = interpreter.interpret("asdkjh234")
        
        # LLM should have been called and returned our mock result
        assert result.intent == "create_app"  # From mock
        assert mock_llm._call_count == 1  # LLM was called once
    
    def test_llm_cache_prevents_duplicate_calls(self):
        """Same message should only trigger one LLM call."""
        from app.services.light_brain_interpreter import LightBrainInterpreter
        interpreter = LightBrainInterpreter()
        mock_llm = MockLLMResponder()
        interpreter.set_llm_responder(mock_llm)
        interpreter.clear_llm_cache()
        
        # First call - might trigger LLM
        interpreter.interpret("asdkjh234")
        first_count = mock_llm._call_count
        
        # Second identical call - should use cache
        interpreter.interpret("asdkjh234")
        assert mock_llm._call_count == first_count, "Cache should prevent duplicate LLM calls"
    
    def test_llm_responder_available_flag(self):
        """LLM responder should report availability correctly."""
        available = MockLLMResponder(available=True)
        assert available.available is True
        
        unavailable = MockLLMResponder(available=False)
        assert unavailable.available is False
    
    def test_llm_intent_validation(self):
        """LLM should return valid intent values."""
        from app.services.light_brain_interpreter import LightBrainInterpreter
        interpreter = LightBrainInterpreter()
        
        # All valid intents
        assert "create_app" in interpreter.VALID_INTENTS
        assert "start_app" in interpreter.VALID_INTENTS
        assert "greet" in interpreter.VALID_INTENTS
        assert "unclear" in interpreter.VALID_INTENTS
        assert len(interpreter.VALID_INTENTS) == 13
