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


def test_code_introspection_prompt_contains_hard_no_guess_rules() -> None:
    interpreter, execute_turns = _build_interpreter()
    execute_turns.return_value = ToolCallingResult(final_text="done", tool_calls=[])

    interpreter.interpret(
        message="查一下 AgentSystem 的持久化是不是 SQLite",
        user_id="u1",
        session_id="sess-1",
        available_apps=[],
    )

    kwargs = execute_turns.call_args.kwargs
    prompt = kwargs["system_prompt"]
    assert "必须先 read_file 读取真实文件内容后才能给出具体实现细节" in prompt
    assert "未 read 文件前,不要断言\"SQLite\"\"MySQL\"\"JSON\"等具体存储类型" in prompt
    assert "如果只搜索了文件名但没 read 内容,不要断言具体实现细节" in prompt


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


def test_process_result_maps_search_only_answer_into_direct_response_but_allows_uncertainty() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(
        final_text="目前只看到了相关文件命中，还没读取文件内容，所以不能确认具体存储实现。",
        tool_calls=[
            ToolCallRecord(
                tool_name="search_files",
                args={"pattern": "persist", "path": "app"},
                result={"success": True, "results": [{"file": "app/services/persistence_service.py"}]},
            )
        ],
    )

    command = interpreter._process_result(result, "查持久化")

    assert command.intent == "direct_response"
    assert "还没读取文件内容" in command.parameters["text"]
    assert "不能确认具体存储实现" in command.parameters["text"]
