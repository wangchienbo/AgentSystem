"""Tests for Dynamic Path Composition — LLM-driven skill chain composition."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.dynamic_path import DynamicPathPlan, DynamicPathStep
from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_meta_service():
    """Mock SkillMetaService with a few skills."""
    meta = MagicMock()
    meta.list_all.return_value = [
        MagicMock(
            skill_id="greet",
            name="greet",
            description="打招呼/问候",
            input_schema={"message": "string"},
            output_schema={"text": "string"},
            actions={},
            offline_capable=True,
        ),
        MagicMock(
            skill_id="query_status",
            name="query_status",
            description="查询系统状态",
            input_schema={},
            output_schema={"status": "string", "apps": "list"},
            actions={},
            offline_capable=True,
        ),
        MagicMock(
            skill_id="create_app",
            name="create_app",
            description="创建 App",
            input_schema={"app_name": "string", "description": "string"},
            output_schema={"app_id": "string"},
            actions={},
            offline_capable=False,
        ),
        MagicMock(
            skill_id="system.universal",
            name="system.universal",
            description="万能兜底技能",
            input_schema={"message": "string"},
            output_schema={"result": "string"},
            actions={"analyze": MagicMock(
                description="分析并处理任意请求",
                input_schema={"message": "string"},
                output_schema={"result": "string"},
            )},
            offline_capable=False,
        ),
    ]
    return meta


@pytest.fixture
def mock_bus():
    """Mock MessageBus."""
    bus = MagicMock()
    bus.list_workers.return_value = ["greet", "query_status", "create_app"]
    bus.rpc = AsyncMock(return_value={
        "skill_id": "greet",
        "status": "completed",
        "output": {"text": "你好！"},
    })
    return bus


@pytest.fixture
def mock_model_router():
    """Mock ModelRouter."""
    router = MagicMock()
    mock_client = MagicMock()
    mock_client.respond = AsyncMock(return_value=json.dumps({
        "goal": "问候并检查状态",
        "reasoning": "用户想打招呼并了解系统状况，需要两个步骤",
        "steps": [
            {
                "skill_id": "greet",
                "action": "execute",
                "input_mapping": {"message": "$user.text"},
                "description": "先打招呼",
            },
            {
                "skill_id": "query_status",
                "action": "execute",
                "input_mapping": {},
                "description": "然后查询系统状态",
            },
        ],
    }))
    router.get_client.return_value = mock_client
    return router


@pytest.fixture
def mock_universal_skill():
    """Mock universal skill."""
    skill = MagicMock()
    skill.process = AsyncMock(return_value=SkillExecutionResult(
        skill_id="system.universal",
        status="completed",
        output={"result": "万能技能处理了请求"},
    ))
    return skill


@pytest.fixture
def composer(mock_meta_service, mock_bus, mock_model_router, mock_universal_skill):
    """Create a DynamicPathComposer with all mocks."""
    from app.services.dynamic_path_composer import DynamicPathComposer
    return DynamicPathComposer(
        skill_meta_service=mock_meta_service,
        message_bus=mock_bus,
        model_router=mock_model_router,
        universal_skill=mock_universal_skill,
    )


# ── Data Model Tests ─────────────────────────────────────────────────────────

class TestDynamicPathStep:
    """Tests for DynamicPathStep model."""

    def test_minimal_step(self):
        step = DynamicPathStep(skill_id="greet")
        assert step.skill_id == "greet"
        assert step.action == "execute"
        assert step.input_mapping == {}

    def test_full_step(self):
        step = DynamicPathStep(
            skill_id="create_app",
            action="execute",
            input_mapping={
                "app_name": "$user.app_name",
                "description": "$user.text",
            },
            description="创建一个新 App",
        )
        assert step.skill_id == "create_app"
        assert step.action == "execute"
        assert len(step.input_mapping) == 2

    def test_step_without_description(self):
        step = DynamicPathStep(skill_id="greet")
        assert step.description == ""


class TestDynamicPathPlan:
    """Tests for DynamicPathPlan model."""

    def test_valid_plan(self):
        plan = DynamicPathPlan(
            goal="问候并检查状态",
            steps=[
                DynamicPathStep(skill_id="greet", action="execute"),
                DynamicPathStep(skill_id="query_status", action="execute"),
            ],
            reasoning="用户需要两个步骤",
        )
        assert plan.goal == "问候并检查状态"
        assert len(plan.steps) == 2

    def test_plan_max_steps(self):
        """Plan should allow up to 10 steps."""
        steps = [DynamicPathStep(skill_id="greet") for _ in range(10)]
        plan = DynamicPathPlan(goal="test", steps=steps)
        assert len(plan.steps) == 10

    def test_plan_too_many_steps(self):
        """Plan should reject more than 10 steps."""
        steps = [DynamicPathStep(skill_id="greet") for _ in range(11)]
        with pytest.raises(Exception):  # pydantic ValidationError
            DynamicPathPlan(goal="test", steps=steps)

    def test_plan_empty_steps(self):
        """Plan should reject empty steps."""
        with pytest.raises(Exception):
            DynamicPathPlan(goal="test", steps=[])

    def test_plan_serialization(self):
        plan = DynamicPathPlan(
            goal="test goal",
            steps=[DynamicPathStep(
                skill_id="greet",
                action="execute",
                input_mapping={"message": "$user.text"},
                description="打招呼",
            )],
            reasoning="because",
        )
        data = plan.model_dump(mode="json")
        assert data["goal"] == "test goal"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["skill_id"] == "greet"


# ── DynamicPathComposer Tests ─────────────────────────────────────────────────

class TestSkillDiscovery:
    """Tests for skill discovery."""

    def test_discovers_skills_from_meta(self, composer, mock_meta_service):
        skills = composer._discover_skills()
        # Should find the 4 skills from meta_service
        skill_ids = {s["skill_id"] for s in skills}
        assert "greet" in skill_ids
        assert "query_status" in skill_ids
        assert "create_app" in skill_ids
        assert "system.universal" in skill_ids

    def test_discovers_skills_include_bus_workers(self, composer, mock_bus):
        mock_bus.list_workers.return_value = ["greet", "new_worker"]
        skills = composer._discover_skills()
        skill_ids = {s["skill_id"] for s in skills}
        # new_worker should be added from bus (not in meta)
        assert "new_worker" in skill_ids

    def test_no_duplicates(self, composer):
        skills = composer._discover_skills()
        skill_ids = [s["skill_id"] for s in skills]
        assert len(skill_ids) == len(set(skill_ids))


class TestLLMPlanning:
    """Tests for LLM-based planning."""

    @pytest.mark.asyncio
    async def test_plan_chain_success(self, composer, mock_model_router):
        plan = await composer._plan_chain("你好，系统怎么样？", [])
        assert plan is not None
        assert plan.goal == "问候并检查状态"
        assert len(plan.steps) == 2

    @pytest.mark.asyncio
    async def test_plan_chain_llm_retry(self, composer, mock_model_router):
        """Should retry on malformed JSON."""
        call_count = 0

        async def failing_respond(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return "not json at all"
            return json.dumps({
                "goal": "retry worked",
                "reasoning": "after retry",
                "steps": [{"skill_id": "greet", "action": "execute"}],
            })

        mock_client = mock_model_router.get_client.return_value
        mock_client.respond = AsyncMock(side_effect=failing_respond)

        plan = await composer._plan_chain("你好", [])
        assert plan is not None
        assert plan.goal == "retry worked"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_plan_chain_all_retries_fail(self, composer, mock_model_router):
        """Should return None after all retries fail."""
        mock_client = mock_model_router.get_client.return_value
        mock_client.respond = AsyncMock(return_value="not json")

        plan = await composer._plan_chain("你好", [])
        assert plan is None

    def test_build_planning_prompt(self, composer):
        skills = [{"skill_id": "greet", "name": "greet", "description": "hi"}]
        prompt = composer._build_planning_prompt("你好", skills)
        assert "你好" in prompt
        assert "greet" in prompt
        assert "skill chain planner" in prompt.lower()

    def test_parse_plan_response_valid(self, composer):
        text = json.dumps({
            "goal": "test",
            "reasoning": "because",
            "steps": [{"skill_id": "greet", "action": "execute"}],
        })
        plan = composer._parse_plan_response(text)
        assert plan is not None
        assert plan.goal == "test"

    def test_parse_plan_response_with_markdown(self, composer):
        text = "```json\n" + json.dumps({
            "goal": "test",
            "reasoning": "because",
            "steps": [{"skill_id": "greet"}],
        }) + "\n```"
        plan = composer._parse_plan_response(text)
        assert plan is not None

    def test_parse_plan_response_invalid(self, composer):
        plan = composer._parse_plan_response("not json")
        assert plan is None

    def test_parse_plan_response_empty_steps(self, composer):
        text = json.dumps({"goal": "test", "steps": []})
        plan = composer._parse_plan_response(text)
        assert plan is None

    def test_parse_plan_response_missing_steps(self, composer):
        text = json.dumps({"goal": "test"})
        plan = composer._parse_plan_response(text)
        assert plan is None


class TestPlanValidation:
    """Tests for plan validation."""

    def test_valid_plan(self, composer):
        skills = [{"skill_id": "greet"}, {"skill_id": "query_status"}]
        plan = DynamicPathPlan(
            goal="test",
            steps=[
                DynamicPathStep(skill_id="greet", input_mapping={"msg": "$user.text"}),
                DynamicPathStep(skill_id="query_status"),
            ],
        )
        valid, error = composer._validate_plan(plan, skills)
        assert valid

    def test_invalid_skill_not_registered(self, composer):
        skills = [{"skill_id": "greet"}]
        plan = DynamicPathPlan(
            goal="test",
            steps=[DynamicPathStep(skill_id="nonexistent")],
        )
        valid, error = composer._validate_plan(plan, skills)
        assert not valid
        assert "nonexistent" in error

    def test_invalid_forward_reference(self, composer):
        skills = [{"skill_id": "greet"}, {"skill_id": "query_status"}]
        plan = DynamicPathPlan(
            goal="test",
            steps=[
                DynamicPathStep(
                    skill_id="greet",
                    input_mapping={"msg": "$step_2.result"},
                ),
                DynamicPathStep(skill_id="query_status"),
            ],
        )
        valid, error = composer._validate_plan(plan, skills)
        assert not valid
        assert "step 2" in error.lower() or "doesn't exist" in error

    def test_valid_backward_reference(self, composer):
        skills = [{"skill_id": "greet"}, {"skill_id": "query_status"}]
        plan = DynamicPathPlan(
            goal="test",
            steps=[
                DynamicPathStep(skill_id="greet"),
                DynamicPathStep(
                    skill_id="query_status",
                    input_mapping={"context": "$step_1"},
                ),
            ],
        )
        valid, error = composer._validate_plan(plan, skills)
        assert valid


class TestInputResolution:
    """Tests for input source resolution."""

    def test_resolve_user_field(self, composer):
        user_data = {"text": "你好", "name": "user"}
        result = composer._resolve_source("$user.text", user_data, {})
        assert result == "你好"

    def test_resolve_user_field_missing(self, composer):
        user_data = {"text": "你好"}
        result = composer._resolve_source("$user.name", user_data, {})
        assert result == "$user.name"  # falls back to literal

    def test_resolve_step_output(self, composer):
        step_outputs = {1: {"text": "greeting", "count": 5}}
        result = composer._resolve_source("$step_1.text", {}, step_outputs)
        assert result == "greeting"

    def test_resolve_full_step_output(self, composer):
        step_outputs = {1: {"text": "greeting", "count": 5}}
        result = composer._resolve_source("$step_1", {}, step_outputs)
        assert result == {"text": "greeting", "count": 5}

    def test_resolve_literal(self, composer):
        result = composer._resolve_source("hello world", {}, {})
        assert result == "hello world"


class TestUserInputParsing:
    """Tests for user input parsing."""

    def test_parse_plain_text(self, composer):
        result = composer._parse_user_input("你好世界")
        assert result["text"] == "你好世界"

    def test_parse_key_value(self, composer):
        text = "app_name: 测试App\ndescription: 这是一个测试"
        result = composer._parse_user_input(text)
        assert result["app_name"] == "测试App"
        assert result["description"] == "这是一个测试"

    def test_parse_chinese_colon(self, composer):
        text = "名称：测试App\n描述：这是一个测试"
        result = composer._parse_user_input(text)
        assert result["名称"] == "测试App" or result.get("名称") == "测试App"


class TestOutputExtraction:
    """Tests for output extraction from RPC results."""

    def test_extract_dict_with_output(self, composer):
        result = composer._extract_output({"output": {"text": "hello"}})
        assert result == {"text": "hello"}

    def test_extract_dict_without_output(self, composer):
        result = composer._extract_output({"status": "completed"})
        assert result == {"status": "completed"}

    def test_extract_string_json(self, composer):
        result = composer._extract_output('{"text": "hello"}')
        assert result == {"text": "hello"}

    def test_extract_string_plain(self, composer):
        result = composer._extract_output("hello world")
        assert result == {"text": "hello world"}

    def test_extract_other_type(self, composer):
        result = composer._extract_output(42)
        assert result == {"value": "42"}


class TestFallback:
    """Tests for universal skill fallback."""

    @pytest.mark.asyncio
    async def test_fallback_to_universal(self, composer, mock_universal_skill):
        result = await composer._fallback("任意请求", "sess-1")
        assert result.status == "completed"
        mock_universal_skill.process.assert_called_once()
        call_args = mock_universal_skill.process.call_args[0][0]
        assert call_args.skill_id == "system.universal"
        assert call_args.action == "analyze"
        assert call_args.inputs["message"] == "任意请求"

    @pytest.mark.asyncio
    async def test_fallback_no_universal(self, mock_meta_service, mock_bus, mock_model_router):
        from app.services.dynamic_path_composer import DynamicPathComposer
        composer = DynamicPathComposer(
            skill_meta_service=mock_meta_service,
            message_bus=mock_bus,
            model_router=mock_model_router,
            universal_skill=None,
        )
        result = await composer._fallback("任意请求", "sess-1")
        assert result.status == "failed"
        assert "无兜底技能" in result.output.get("error", "")


class TestComposeAndExecute:
    """Integration tests for the full compose-and-execute flow."""

    @pytest.mark.asyncio
    async def test_full_flow_success(self, composer, mock_bus):
        mock_bus.rpc = AsyncMock(return_value={
            "status": "completed",
            "output": {"text": "你好！"},
        })
        result = await composer.compose_and_execute(
            "你好",
            session_id="sess-1",
            user_id="user-1",
        )
        assert result is not None
        # Should succeed with dynamic composition or fallback

    @pytest.mark.asyncio
    async def test_no_skills_available(self, composer, mock_meta_service):
        mock_meta_service.list_all.return_value = []
        composer._bus.list_workers.return_value = []
        result = await composer.compose_and_execute("你好")
        assert result is None

    @pytest.mark.asyncio
    async def test_execution_step_failure(self, composer, mock_bus):
        mock_bus.rpc = AsyncMock(return_value={
            "status": "failed",
            "error": "skill error",
        })
        result = await composer.compose_and_execute("你好", session_id="sess-1")
        # Should return failed result or fallback
        assert result is not None


# ── AppOrchestrator Integration ──────────────────────────────────────────────

class TestAppOrchestratorDynamicPath:
    """Tests for AppOrchestrator integration with DynamicPathComposer."""

    @pytest.mark.asyncio
    async def test_orchestrator_uses_dynamic_composer(self):
        """When no YAML path matches, orchestrator should try dynamic composition."""
        from app.services.app_orchestrator import AppOrchestrator
        from app.services.path_store import PathStore

        mock_bus = MagicMock()
        mock_bus.list_workers.return_value = []

        mock_composer = AsyncMock()
        mock_composer.compose_and_execute.return_value = SkillExecutionResult(
            skill_id="dynamic_path_composer",
            status="completed",
            output={"result": "dynamic result"},
        )

        path_store = MagicMock()
        path_store.load_all.return_value = {}  # No YAML paths

        orch = AppOrchestrator(
            bus=mock_bus,
            path_store=path_store,
            dynamic_composer=mock_composer,
        )
        orch._paths = {}

        request = SkillExecutionRequest(
            skill_id="__gateway__",
            inputs={"message": "帮我查一下系统状态"},
            config={"session_id": "sess-1"},
            user_id="user-1",
            app_instance_id="test-app",
            workflow_id="test-workflow",
            step_id="test-step",
        )

        result = await orch.process(request)

        mock_composer.compose_and_execute.assert_called_once()
        assert result.status == "completed"
        assert result.output.get("result") == "dynamic result"

    @pytest.mark.asyncio
    async def test_orchestrator_falls_back_when_composer_fails(self):
        """When dynamic composition fails, should fall back to universal."""
        from app.services.app_orchestrator import AppOrchestrator
        from app.services.path_store import PathStore

        mock_bus = MagicMock()
        mock_bus.list_workers.return_value = []

        mock_composer = AsyncMock()
        mock_composer.compose_and_execute.return_value = SkillExecutionResult(
            skill_id="dynamic_path_composer",
            status="failed",
            output={"error": "no skills available"},
            error="no skills",
        )

        mock_universal = AsyncMock()
        mock_universal.process.return_value = SkillExecutionResult(
            skill_id="system.universal",
            status="completed",
            output={"result": "universal handled it"},
        )

        path_store = MagicMock()
        path_store.load_all.return_value = {}

        orch = AppOrchestrator(
            bus=mock_bus,
            path_store=path_store,
            dynamic_composer=mock_composer,
            universal_skill=mock_universal,
        )
        orch._paths = {}

        request = SkillExecutionRequest(
            skill_id="__gateway__",
            inputs={"message": "随便什么请求"},
            config={"session_id": "sess-1"},
            user_id="user-1",
            app_instance_id="test-app",
            workflow_id="test-workflow",
            step_id="test-step",
        )

        result = await orch.process(request)

        # Dynamic composition was tried
        mock_composer.compose_and_execute.assert_called_once()
        # Universal fallback was used
        mock_universal.process.assert_called_once()
        assert result.status == "completed"
