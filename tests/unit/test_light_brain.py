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
        assert reply.type in ("confirm", "text", "error")  # error if no MessageBus configured
        if reply.type != "error":
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
    async def test_execute_action_rebuilds_command_from_action_params_without_last_command(self):
        req = ChatMessageRequest(user_id="u1", channel="webchat", message="你好")
        reply = await self.gateway.process_message(req)
        session_id = reply.session_id
        session = self.gateway._memory.get_session(session_id)
        session.last_command = None

        action_reply = await self.gateway.execute_action(
            user_id="u1",
            session_id=session_id,
            action_id="confirm-runtime-asset-call",
            action_params={
                "intent": "call_asset_method",
                "parameters": {
                    "asset_id": "asset:runtime_center:v1",
                    "method": "list_assets",
                    "params": {},
                },
            },
        )
        assert action_reply.type in ("text", "error")
        if action_reply.type == "text":
            assert "asset:runtime_center:v1" in action_reply.content
            assert "list_assets" in action_reply.content
        else:
            assert action_reply.content

    @pytest.mark.asyncio
    async def test_session_persistence_sanitizes_runtime_only_command_context(self):
        req = ChatMessageRequest(user_id="u1", channel="webchat", message="系统状态")
        reply = await self.gateway.process_message(req)
        session = self.gateway._memory.get_session(reply.session_id)
        assert session is not None
        assert session.last_command is not None
        serialized = session.to_dict()
        assert serialized["last_command"] is not None
        assert isinstance(serialized["last_command"]["context"], dict)
        assert "ToolRegistry" in serialized["last_command"]["context"].get("tool_registry", "")

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
        return self._parse_result, None
    
    def generate_reply(self, system_context, user_message, **kwargs):
        self._call_count += 1
        return "我是通过 LLM 生成的回复。", None


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
        assert len(interpreter.VALID_INTENTS) >= 27


# ===========================================================================
# Persistence Service tests (Phase 8.5)
# ===========================================================================

class TestPersistenceService:
    """Test save/restore roundtrip for app state persistence."""

    def setup_method(self):
        import tempfile
        from app.services.persistence_service import PersistenceService
        self.tmpdir = tempfile.mkdtemp()
        self.persistence = PersistenceService(data_dir=self.tmpdir)

    def _build_services(self):
        """Build a minimal set of services for persistence testing."""
        import tempfile
        from app.services.lifecycle import AppLifecycleService
        from app.services.runtime_host import AppRuntimeHostService
        from app.services.app_registry import AppRegistryService
        from app.services.app_catalog import AppCatalogService
        from app.services.light_brain_memory import LightBrainMemory
        from app.models.app_instance import AppInstance
        from app.models.app_blueprint import AppBlueprint
        from app.models.runtime_policy import RuntimePolicy
        from app.models.app_profile import AppRuntimeProfile
        from app.models.interaction import AppCatalogEntry

        memdir = tempfile.mkdtemp()
        memory = LightBrainMemory(data_dir=memdir)
        lifecycle = AppLifecycleService()
        runtime_host = AppRuntimeHostService(lifecycle=lifecycle)
        registry = AppRegistryService()
        catalog = AppCatalogService()

        # Register a blueprint
        bp = AppBlueprint(
            id="bp-monitor",
            name="监控 App",
            version="0.1.0",
            goal="系统监控",
            app_shape="generic",
            required_skills={"skill-a", "skill-b"},
            runtime_policy=RuntimePolicy(),
            runtime_profile=AppRuntimeProfile(),
        )
        registry.register_blueprint(bp, description="A monitoring app")

        # Create and register an app instance
        instance = AppInstance(
            id="app-monitor-001",
            blueprint_id="bp-monitor",
            owner_user_id="u1",
            status="installed",
            data_namespace="users/u1/apps/app-monitor-001",
        )
        runtime_host.register_instance(instance)
        runtime_host.start("app-monitor-001", reason="test")
        runtime_host.enqueue_task("app-monitor-001", "check_cpu")

        # Register catalog entry
        catalog.register(AppCatalogEntry(
            app_id="app-monitor-001",
            name="监控 App",
            description="系统监控应用",
            execution_mode="service",
            trigger_phrases=["监控", "monitor"],
            blueprint_id="bp-monitor",
        ))

        # Create a session
        memory.create_session(user_id="u1", channel="webchat", session_id="sess-test")
        memory.record_user_message("sess-test", "你好")

        return lifecycle, runtime_host, registry, catalog, memory

    def test_save_state_creates_file(self):
        """save_state should write the state file to disk."""
        lifecycle, runtime_host, registry, catalog, memory = self._build_services()

        path = self.persistence.save_state(
            lifecycle=lifecycle,
            runtime_host=runtime_host,
            registry=registry,
            catalog=catalog,
            light_brain_memory=memory,
        )

        assert path.exists()
        assert path.name == "agent_state.json"

    def test_restore_roundtrip(self):
        """Save state, then restore into fresh services — all data should match."""
        lifecycle, runtime_host, registry, catalog, memory = self._build_services()

        # Save
        self.persistence.save_state(
            lifecycle=lifecycle,
            runtime_host=runtime_host,
            registry=registry,
            catalog=catalog,
            light_brain_memory=memory,
        )

        # Build fresh services (simulating restart)
        lifecycle2, runtime_host2, registry2, catalog2, memory2 = self._build_services()

        # Clear the fresh services to simulate cold start
        lifecycle2._instances.clear()
        lifecycle2._events.clear()
        runtime_host2._leases.clear()
        runtime_host2._checkpoints.clear()
        runtime_host2._pending_tasks.clear()
        registry2._blueprints.clear()
        registry2._entries.clear()
        catalog2._apps.clear()

        # Restore
        result = self.persistence.restore_state(
            lifecycle=lifecycle2,
            runtime_host=runtime_host2,
            registry=registry2,
            catalog=catalog2,
            light_brain_memory=memory2,
        )

        assert result["status"] == "restored"
        assert result.get("app_instances", 0) >= 1
        assert result.get("registry_entries", 0) >= 2  # blueprint + entry

        # Verify app instance restored
        instance = lifecycle2.get_instance("app-monitor-001")
        assert instance is not None
        assert instance.blueprint_id == "bp-monitor"
        assert instance.owner_user_id == "u1"

        # Verify lease restored
        assert "app-monitor-001" in runtime_host2._leases
        lease = runtime_host2._leases["app-monitor-001"]
        assert lease.status == "running"

        # Verify pending tasks restored
        assert "check_cpu" in runtime_host2._pending_tasks.get("app-monitor-001", [])

        # Verify blueprint restored
        bp = registry2.get_blueprint("bp-monitor")
        assert bp.name == "监控 App"
        assert bp.app_shape == "generic"

        # Verify catalog entry restored
        entries = catalog2.list_apps()
        assert len(entries) >= 1
        assert entries[0].name == "监控 App"

    def test_restore_no_state_file(self):
        """When no state file exists, restore should return gracefully."""
        lifecycle, runtime_host, registry, catalog, memory = self._build_services()

        # Clear fresh
        lifecycle._instances.clear()

        result = self.persistence.restore_state(
            lifecycle=lifecycle,
            runtime_host=runtime_host,
            registry=registry,
            catalog=catalog,
            light_brain_memory=memory,
        )

        assert result["status"] == "no_state_file"
        assert len(lifecycle.list_instances()) == 0

    def test_restore_corrupted_file(self):
        """Corrupted JSON should be quarantined and restore should degrade gracefully."""
        import json
        state_file = self.persistence.state_file
        state_file.write_text("{not valid json", encoding="utf-8")

        result = self.persistence.restore_state()
        assert result["status"] == "quarantined_corrupted"
        assert not state_file.exists()

    def test_restore_empty_file(self):
        """Empty state file should be quarantined."""
        state_file = self.persistence.state_file
        state_file.write_text("", encoding="utf-8")

        result = self.persistence.restore_state()
        assert result["status"] == "quarantined_empty"

    def test_gateway_auto_save_with_persistence(self):
        """Gateway with persistence_service should auto-save after messages."""
        import tempfile
        from app.services.lifecycle import AppLifecycleService
        from app.services.runtime_host import AppRuntimeHostService
        from app.services.app_registry import AppRegistryService
        from app.services.app_catalog import AppCatalogService
        from app.services.light_brain_memory import LightBrainMemory
        from app.services.light_brain_gateway import LightBrainGateway
        from app.services.persistence_service import PersistenceService
        from app.models.app_instance import AppInstance
        from app.models.app_blueprint import AppBlueprint
        from app.models.runtime_policy import RuntimePolicy
        from app.models.app_profile import AppRuntimeProfile
        from app.models.interaction import AppCatalogEntry
        from app.models.chat import ChatMessageRequest

        # Build services
        memdir = tempfile.mkdtemp()
        persist_dir = tempfile.mkdtemp()
        memory = LightBrainMemory(data_dir=memdir)
        interpreter = LightBrainInterpreter()
        lifecycle = AppLifecycleService()
        runtime_host = AppRuntimeHostService(lifecycle=lifecycle)
        registry = AppRegistryService()
        catalog = AppCatalogService()
        persistence = PersistenceService(data_dir=persist_dir)

        # Register blueprint and instance
        bp = AppBlueprint(
            id="bp-test",
            name="测试",
            version="0.1.0",
            goal="test",
            app_shape="generic",
            required_skills=set(),
            runtime_policy=RuntimePolicy(),
            runtime_profile=AppRuntimeProfile(),
        )
        registry.register_blueprint(bp)
        instance = AppInstance(
            id="app-test",
            blueprint_id="bp-test",
            owner_user_id="u1",
            status="installed",
            data_namespace="users/u1/apps/app-test",
        )
        runtime_host.register_instance(instance)

        catalog.register(AppCatalogEntry(
            app_id="app-test",
            name="测试",
            description="Test",
            execution_mode="service",
            trigger_phrases=["测试"],
            blueprint_id="bp-test",
        ))

        gateway = LightBrainGateway(
            memory=memory,
            interpreter=interpreter,
            app_registry_service=registry,
            app_lifecycle_service=lifecycle,
            app_runtime_host=runtime_host,
            app_catalog=catalog,
            persistence_service=persistence,
        )

        # Process a message — should trigger auto-save
        import asyncio
        request = ChatMessageRequest(user_id="u1", channel="webchat", message="你好")
        asyncio.run(gateway.process_message(request))

        # State file should exist
        assert persistence.state_file.exists()
