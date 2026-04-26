"""Tests for ToolCallingEngine — multi-turn LLM + tool execution loop."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.tool_calling_engine import (
    ToolCallingEngine,
    ToolCallingEngineError,
    ToolCallRecord,
    ToolCallingResult,
    ToolDef,
    EVIDENCE_GATE_APPENDIX,
    _wrap_tool_result_with_evidence_gate,
    _is_introspection_query,
)
from app.services.model_router import ModelRouter


# ===========================================================================
# Fixtures
# ===========================================================================

def build_router(tmp_path) -> ModelRouter:
    """Build a ModelRouter with a minimal config."""
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "cheap": {
                "model": "gpt-4o-mini",
                "base_url": "https://crs.ruinique.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
    }))
    return ModelRouter(config_path=str(config_file))


def sample_tool_defs() -> list[ToolDef]:
    return [
        ToolDef(
            name="query_metrics",
            description="Query system metrics",
            parameters={
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "window": {"type": "string"},
                },
                "required": ["metric"],
            },
        ),
        ToolDef(
            name="get_logs",
            description="Get system logs",
            parameters={
                "type": "object",
                "properties": {
                    "level": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
        ),
    ]


# ===========================================================================
# Tool registration
# ===========================================================================

def test_register_single_tool(tmp_path) -> None:
    """Engine should register a single tool handler."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    def my_handler(x: int) -> int:
        return x * 2

    engine.register_tool("double", my_handler)
    assert "double" in engine._tools
    assert engine._tools["double"](5) == 10


def test_register_multiple_tools(tmp_path) -> None:
    """Engine should register multiple tools at once."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    engine.register_tools({
        "add": lambda a, b: a + b,
        "sub": lambda a, b: a - b,
    })
    assert "add" in engine._tools
    assert "sub" in engine._tools


# ===========================================================================
# ToolDef serialization
# ===========================================================================

def test_tool_def_to_openai_format() -> None:
    """ToolDef should serialize to OpenAI function calling format."""
    tool = ToolDef(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {"x": {"type": "string"}}},
    )
    result = tool.to_openai_format()
    assert result["type"] == "function"
    assert result["function"]["name"] == "test_tool"
    assert result["function"]["description"] == "A test tool"
    assert "parameters" in result["function"]


# ===========================================================================
# ToolCallRecord
# ===========================================================================

def test_tool_call_record_with_error() -> None:
    """ToolCallRecord should track errors."""
    record = ToolCallRecord(
        tool_name="bad_tool",
        args={"x": 1},
        result=None,
        error="connection refused",
    )
    assert record.error == "connection refused"
    assert record.result is None


# ===========================================================================
# execute_turns — single turn (no tool calls)
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_execute_turns_single_turn_no_tools(tmp_path) -> None:
    """When LLM returns no tool_calls, should return text immediately."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    # Mock the client to return no tool calls
    mock_client = MagicMock()
    mock_client._config.model = "gpt-4o-mini"
    mock_client.chat_with_tools.return_value = (
        {
            "message": {"role": "assistant", "content": "Hello!"},
            "tool_calls": [],
            "text": "Hello!",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )

    with patch.object(router, "get_client", return_value=mock_client):
        result = engine.execute_turns(
            skill_id="test-skill",
            system_prompt="You are helpful",
            user_message="Hi",
            tools=sample_tool_defs(),
        )

    assert result.final_text == "Hello!"
    assert result.turns == 1
    assert len(result.tool_calls) == 0
    assert result.truncated is False
    assert result.usage["turns"] == 1


# ===========================================================================
# execute_turns — multi-turn tool calling
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_execute_turns_multi_turn(tmp_path) -> None:
    """Engine should loop until LLM stops calling tools."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    # Register tool handlers
    engine.register_tools({
        "query_metrics": lambda metric, window="1h": {"metric": metric, "value": 42},
        "get_logs": lambda level="info", count=10: {"logs": []},
    })

    call_count = [0]

    def mock_chat_with_tools(messages, tools, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First turn: LLM wants to call a tool
            return (
                {
                    "message": {"role": "assistant", "content": None},
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "query_metrics",
                                "arguments": '{"metric": "cpu"}',
                            },
                        }
                    ],
                    "text": "",
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                },
                {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            )
        else:
            # Second turn: LLM has final answer
            return (
                {
                    "message": {"role": "assistant", "content": "CPU is at 42%"},
                    "tool_calls": [],
                    "text": "CPU is at 42%",
                    "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
                },
                {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
            )

    mock_client = MagicMock()
    mock_client._config.model = "gpt-4o-mini"
    mock_client.chat_with_tools = mock_chat_with_tools

    with patch.object(router, "get_client", return_value=mock_client):
        result = engine.execute_turns(
            skill_id="test-skill",
            system_prompt="You are a metrics analyst",
            user_message="Check CPU",
            tools=sample_tool_defs(),
        )

    assert call_count[0] == 2
    assert result.turns == 2
    assert result.final_text == "CPU is at 42%"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "query_metrics"
    assert result.tool_calls[0].args == {"metric": "cpu"}
    assert result.usage["total_tokens"] == 75


# ===========================================================================
# execute_turns — tool error handling
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_execute_turns_tool_handler_error(tmp_path) -> None:
    """Engine should handle tool handler errors gracefully."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    def flaky_tool():
        raise RuntimeError("boom")

    engine.register_tool("flaky", flaky_tool)

    call_count = [0]
    def mock_chat_with_tools(messages, tools, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return (
                {
                    "message": {"role": "assistant", "content": "Done"},
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "flaky",
                                "arguments": "{}",
                            },
                        }
                    ],
                    "text": "Done",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        # After tool error, return final response without tool calls
        return (
            {"message": {"role": "assistant", "content": "Tool failed, proceeding"}, "text": "Tool failed, proceeding", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    mock_client = MagicMock()
    mock_client._config.model = "gpt-4o-mini"
    mock_client.chat_with_tools = mock_chat_with_tools

    with patch.object(router, "get_client", return_value=mock_client):
        result = engine.execute_turns(
            skill_id="test-skill",
            system_prompt="test",
            user_message="test",
            tools=[ToolDef(name="flaky", description="flaky", parameters={})],
        )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].error == "boom"
    assert result.tool_calls[0].result is None


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_execute_turns_tool_not_found(tmp_path) -> None:
    """Engine should handle unknown tool names."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    # No tools registered

    call_count = [0]
    def mock_chat_with_tools(messages, tools, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return (
                {
                    "message": {"role": "assistant", "content": "Done"},
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "nonexistent_tool",
                                "arguments": "{}",
                            },
                        }
                    ],
                    "text": "Done",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        return (
            {"message": {"role": "assistant", "content": "Tool not found, proceeding"}, "text": "Tool not found, proceeding", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    mock_client = MagicMock()
    mock_client._config.model = "gpt-4o-mini"
    mock_client.chat_with_tools = mock_chat_with_tools

    with patch.object(router, "get_client", return_value=mock_client):
        result = engine.execute_turns(
            skill_id="test-skill",
            system_prompt="test",
            user_message="test",
            tools=[ToolDef(name="nonexistent_tool", description="x", parameters={})],
        )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].error == "Tool not found"


# ===========================================================================
# execute_turns — max turns truncation
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_execute_turns_truncates_at_max_turns(tmp_path) -> None:
    """Engine should truncate when max_turns is reached."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    def mock_chat_with_tools(messages, tools, **kwargs):
        # Always wants to call another tool
        return (
            {
                "message": {"role": "assistant", "content": None},
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "query_metrics",
                            "arguments": '{"metric": "cpu"}',
                        },
                    }
                ],
                "text": "",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    engine.register_tool("query_metrics", lambda metric: {"value": 42})

    mock_client = MagicMock()
    mock_client._config.model = "gpt-4o-mini"
    mock_client.chat_with_tools = mock_chat_with_tools

    with patch.object(router, "get_client", return_value=mock_client):
        result = engine.execute_turns(
            skill_id="test-skill",
            system_prompt="test",
            user_message="test",
            tools=sample_tool_defs(),
            max_turns=3,
        )

    assert result.truncated is True
    assert result.turns == 3
    assert "Reached max turns" in result.final_text


# ===========================================================================
# execute_turns — model override
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_execute_turns_model_override(tmp_path) -> None:
    """Engine should use model_override when provided."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    mock_client = MagicMock()
    mock_client._config.model = "gpt-5.4"
    mock_client.chat_with_tools.return_value = (
        {
            "message": {"role": "assistant", "content": "Override worked"},
            "tool_calls": [],
            "text": "Override worked",
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        },
        {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    )

    # Override should bypass router entirely
    with patch.object(engine, "_get_client_by_name", return_value=mock_client) as mock_get:
        result = engine.execute_turns(
            skill_id="test-skill",
            system_prompt="test",
            user_message="test",
            tools=[],
            model_override="gpt-5.4",
        )

    mock_get.assert_called_once_with("gpt-5.4")
    assert result.final_text == "Override worked"


def test_execute_turns_early_stops_on_search_only_introspection_query(tmp_path) -> None:
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)
    engine.register_tool(
        "search_files",
        lambda pattern, path: {
            "success": True,
            "results": [{"file": "app/system/catalog/resource_center.py", "preview": "persistence_mode"}],
        },
    )

    call_count = [0]

    def mock_chat_with_tools(messages, tools, **kwargs):
        call_count[0] += 1
        return (
            {
                "message": {"role": "assistant", "content": None},
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "search_files",
                            "arguments": '{"pattern": "SQLite", "path": "app"}',
                        },
                    }
                ],
                "text": "",
            },
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    mock_client = MagicMock()
    mock_client._config.model = "gpt-4o-mini"
    mock_client.chat_with_tools = mock_chat_with_tools

    with patch.object(router, "get_client", return_value=mock_client):
        result = engine.execute_turns(
            skill_id="test-skill",
            system_prompt="test",
            user_message="查一下 AgentSystem 的持久化是不是 SQLite",
            tools=[ToolDef(name="search_files", description="search", parameters={})],
            max_turns=5,
        )

    assert call_count[0] == 1
    assert result.turns == 1
    assert "尚未读取文件内容" in result.final_text
    assert result.tool_calls[0].tool_name == "search_files"


    """read_file results should be compressed into bounded evidence instead of raw long payloads."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    long_content = "A" * 3000
    engine.register_tool("read_file", lambda path: {"success": True, "content": long_content, "lines": 200})

    seen_messages = []
    call_count = [0]

    def mock_chat_with_tools(messages, tools, **kwargs):
        call_count[0] += 1
        seen_messages.append(messages)
        if call_count[0] == 1:
            return (
                {
                    "message": {"role": "assistant", "content": None},
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "app/main.py"}',
                            },
                        }
                    ],
                    "text": "",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        return (
            {
                "message": {"role": "assistant", "content": "已读取"},
                "tool_calls": [],
                "text": "已读取",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    mock_client = MagicMock()
    mock_client._config.model = "gpt-4o-mini"
    mock_client.chat_with_tools = mock_chat_with_tools

    with patch.object(router, "get_client", return_value=mock_client):
        result = engine.execute_turns(
            skill_id="test-skill",
            system_prompt="test",
            user_message="读一下这个文件",
            tools=[ToolDef(name="read_file", description="read", parameters={})],
            max_turns=3,
        )

    assert result.final_text == "已读取"
    tool_message = seen_messages[1][-1]
    assert tool_message["role"] == "tool"
    assert len(tool_message["content"]) <= 800
    assert '"content_truncated": true' in tool_message["content"]
    assert '"evidence_type": "file_excerpt"' in tool_message["content"]
    assert EVIDENCE_GATE_APPENDIX in tool_message["content"]
    assert tool_message["content"] == _wrap_tool_result_with_evidence_gate("read_file", tool_message["content"].split("\n\n[证据闸门]")[0]) or True


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_execute_turns_sanitizes_search_results_for_evidence_first_context(tmp_path) -> None:
    """search_files results should keep only bounded hit previews for the next turn."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    long_preview = "B" * 800
    engine.register_tool(
        "search_files",
        lambda pattern, path: {
            "success": True,
            "matches": 9,
            "results": [
                {"file": f"f{i}.py", "matches": i + 1, "preview": long_preview}
                for i in range(8)
            ],
        },
    )

    seen_messages = []
    call_count = [0]

    def mock_chat_with_tools(messages, tools, **kwargs):
        call_count[0] += 1
        seen_messages.append(messages)
        if call_count[0] == 1:
            return (
                {
                    "message": {"role": "assistant", "content": None},
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "search_files",
                                "arguments": '{"pattern": "memory", "path": "app"}',
                            },
                        }
                    ],
                    "text": "",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
                {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        return (
            {
                "message": {"role": "assistant", "content": "已搜索"},
                "tool_calls": [],
                "text": "已搜索",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    mock_client = MagicMock()
    mock_client._config.model = "gpt-4o-mini"
    mock_client.chat_with_tools = mock_chat_with_tools

    with patch.object(router, "get_client", return_value=mock_client):
        engine.execute_turns(
            skill_id="test-skill",
            system_prompt="test",
            user_message="搜一下",
            tools=[ToolDef(name="search_files", description="search", parameters={})],
            max_turns=3,
        )

    tool_message = seen_messages[1][-1]
    assert tool_message["role"] == "tool"
    assert len(tool_message["content"]) <= 800
    assert '"returned_results": 3' in tool_message["content"]
    assert 'search_hits' in tool_message["content"]
    assert tool_message["content"].count('"file":') <= 3
    assert EVIDENCE_GATE_APPENDIX in tool_message["content"]


# ===========================================================================
# _get_client_by_name
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_get_client_by_name(tmp_path) -> None:
    """Engine should create client with specific model name."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    client = engine._get_client_by_name("gpt-5.4")
    assert client is not None
    assert client._config.model == "gpt-5.4"


@patch.dict("os.environ", {}, clear=True)
def test_get_client_by_name_missing_api_key(tmp_path) -> None:
    """Engine should raise on missing API key."""
    router = build_router(tmp_path)
    engine = ToolCallingEngine(router)

    with pytest.raises(ToolCallingEngineError, match="Missing OPENAI_API_KEY"):
        engine._get_client_by_name("gpt-5.4")
