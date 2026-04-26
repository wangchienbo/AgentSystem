from __future__ import annotations

from unittest.mock import MagicMock

from app.models.chat import InterpretedCommand
from app.services.light_brain_memory import LightBrainMemory
from app.services.tool_registry import ToolRegistry
from app.services.tool_calling_engine import ToolCallingEngine, ToolCallingResult, ToolCallRecord
from app.services.model_router import ModelRouter
from app.system.gateway.tool_calling_interpreter import ToolCallingInterpreter


class DummyRouter(ModelRouter):
    def __init__(self):
        pass


def _build_interpreter() -> tuple[ToolCallingInterpreter, MagicMock]:
    memory = LightBrainMemory()
    registry = ToolRegistry()
    engine = ToolCallingEngine(DummyRouter())
    engine.execute_turns = MagicMock()
    interpreter = ToolCallingInterpreter(
        tool_registry=registry,
        tool_calling_engine=engine,
        memory=memory,
    )
    return interpreter, engine.execute_turns


def test_explicit_file_path_introspection_uses_fast_read_path() -> None:
    interpreter, execute_turns = _build_interpreter()
    execute_turns.return_value = ToolCallingResult(
        final_text="我已读取 resource_center.py，其中 persistence_mode 默认值是 json。",
        tool_calls=[
            ToolCallRecord(
                tool_name="read_file",
                args={"path": "app/system/catalog/resource_center.py"},
                result={"success": True, "content": 'persistence_mode: str = \"json\"'},
            )
        ],
    )

    command = interpreter.interpret(
        message="请直接读取 app/system/catalog/resource_center.py，并告诉我 persistence_mode 默认值，只回答已证实内容",
        user_id="u1",
        session_id="sess-1",
        available_apps=[],
    )

    kwargs = execute_turns.call_args.kwargs
    assert kwargs["max_turns"] == 20
    assert command.intent == "direct_response"
    assert "json" in command.parameters["text"]


def test_process_result_preserves_evidence_bounded_final_text_without_guessing() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(
        final_text="已读取 persistence_service.py。当前已查文件中未证实 SQLite，只能确认存在持久化处理逻辑。",
        tool_calls=[
            ToolCallRecord(
                tool_name="read_file",
                args={"path": "app/services/persistence_service.py"},
                result={"success": True, "content": "..."},
            )
        ],
    )

    command = interpreter._process_result(result, "持久化用的是什么")

    assert isinstance(command, InterpretedCommand)
    assert command.intent == "direct_response"
    assert "未证实 SQLite" in command.parameters["text"]
    assert "read_file" not in command.parameters["text"]


def test_process_result_returns_final_text_without_tool_specific_gating() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(
        final_text="根据已搜索到的内容，在某文件中发现了 JSON 默认值。",
        tool_calls=[
            ToolCallRecord(
                tool_name="search_files",
                args={"pattern": "persist", "path": "app"},
                result={"success": True, "results": [{"file": "app/services/persistence_service.py"}]},
            )
        ],
    )

    command = interpreter._process_result(result, "查一下 AgentSystem 的持久化是不是 SQLite")

    assert command.intent == "direct_response"
    assert command.parameters["text"] == "根据已搜索到的内容，在某文件中发现了 JSON 默认值。"


def test_process_result_preserves_truncated_text_without_special_introspection_rewrite() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(
        final_text="[Reached max turns (20)]",
        tool_calls=[],
        turns=20,
        truncated=True,
    )

    command = interpreter._process_result(result, "查一下 AgentSystem 的持久化是不是 SQLite")

    assert command.intent == "direct_response"
    assert command.parameters["text"] == "[Reached max turns (20)]"


