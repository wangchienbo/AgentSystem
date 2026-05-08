from __future__ import annotations

import json

from unittest.mock import MagicMock, patch

from app.models.chat import InterpretedCommand
from app.services.light_brain_memory import LightBrainMemory
from app.services.tool_registry import ToolRegistry
from app.services.tool_calling_engine import ToolCallingEngine, ToolCallingResult, ToolCallRecord, ToolDef
from app.system.master.tool_registry import ToolDefinition
from app.services.model_router import ModelRouter
from app.system.gateway.scan_profiles import SCAN_PROFILES, derive_scan_profile
from app.system.gateway.tool_calling_interpreter import (
    ToolCallingInterpreter,
    build_turn_state_board,
    choose_turn_budget,
    is_script_like_request,
    narrow_tools_for_script_route,
)


class DummyRouter(ModelRouter):
    def __init__(self):
        pass


def test_derive_scan_profile_detects_router_config_schema_runtime_topics() -> None:
    assert derive_scan_profile("请遍历路由定义并汇总接口") is not None
    assert derive_scan_profile("请扫描配置和 env 使用") is not None
    assert derive_scan_profile("请汇总数据模型和字段定义") is not None
    assert derive_scan_profile("请分析 runtime worker 启动流程") is not None
    assert derive_scan_profile("请检查校验器和 guard 规则") is not None
    assert derive_scan_profile("请检查日志埋点和观测记录") is not None
    assert derive_scan_profile("请梳理 API handler 和 request/response 流程") is not None
    assert derive_scan_profile("请检查 storage backend 和读写路径") is not None


def test_scan_profiles_define_scope_metadata() -> None:
    api_profile = next(p for p in SCAN_PROFILES if p["name"] == "api")
    assert api_profile["scan_roots"]
    assert ".py" in api_profile["file_extensions"]
    assert api_profile["max_files"] > 0
    assert api_profile["max_hits_per_file"] > 0
    assert api_profile["max_rows"] > 0


def test_build_turn_state_board_adds_script_escalation_hint_after_non_convergence() -> None:
    board = build_turn_state_board(
        "请写个脚本遍历目录并聚合结果",
        [
            {"role": "user", "content": "请遍历 persistence 相关文件"},
            {"role": "assistant", "content": "[Reached max turns (10)]"},
        ],
    )
    assert "exec_shell" in board
    assert "升级规则" in board


def test_is_script_like_request_detects_aggregation_shape() -> None:
    assert is_script_like_request("请遍历目录并汇总 persistence 定义") is True
    assert is_script_like_request("你好") is False


def test_script_route_tool_narrowing_keeps_exec_shell_and_core_file_tools() -> None:
    narrowed = narrow_tools_for_script_route([
        ToolDef(name="exec_shell", description="", parameters={}),
        ToolDef(name="read_file", description="", parameters={}),
        ToolDef(name="search_files", description="", parameters={}),
        ToolDef(name="unclear", description="", parameters={}),
    ])
    names = [t.name for t in narrowed]
    assert "exec_shell" in names
    assert "read_file" in names
    assert "search_files" not in names





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


def test_deterministic_prestep_injects_profile_focus_and_template() -> None:
    interpreter, execute_turns = _build_interpreter()
    execute_turns.return_value = ToolCallingResult(final_text="已基于脚本结果完成汇总", tool_calls=[])
    with patch("app.system.gateway.tool_calling_interpreter.exec_shell", return_value={"success": True, "stdout": "[]"}):
        interpreter.interpret(
            message="请检查日志埋点和观测记录，并汇总 telemetry 调用链",
            user_id="u1",
            session_id="sess-telemetry",
            available_apps=[],
        )
    system_prompt = execute_turns.call_args.kwargs["system_prompt"]
    assert "本次汇总重点" in system_prompt
    assert "输出模板要求" in system_prompt
    assert "观测组件" in system_prompt


def test_deterministic_prestep_records_telemetry_when_available() -> None:
    interpreter, execute_turns = _build_interpreter()
    interpreter._telemetry_service = MagicMock()
    execute_turns.return_value = ToolCallingResult(final_text="已基于脚本结果完成汇总", tool_calls=[])
    with patch("app.system.gateway.tool_calling_interpreter.exec_shell", return_value={"success": True, "stdout": "[]"}):
        interpreter.interpret(
            message="请遍历 app 目录并检查 storage backend 和读写路径，再汇总结果",
            user_id="u1",
            session_id="sess-telemetry-record",
            available_apps=[],
        )
    assert interpreter._telemetry_service.record_step.called is True


def test_persistence_script_route_uses_deterministic_prestep_when_shell_succeeds() -> None:
    interpreter, execute_turns = _build_interpreter()
    execute_turns.return_value = ToolCallingResult(final_text="已基于脚本结果完成汇总", tool_calls=[])
    with patch("app.system.gateway.tool_calling_interpreter.exec_shell", return_value={"success": True, "stdout": "[]"}):
        command = interpreter.interpret(
            message="请遍历 app 目录并汇总 persistence 定义，如果太碎就先写脚本再执行",
            user_id="u1",
            session_id="sess-prestep",
            available_apps=[],
        )
    kwargs = execute_turns.call_args.kwargs
    assert kwargs["skill_id"] == "gateway_script_prestep_summarizer"
    assert kwargs["max_turns"] == 1
    assert command.intent == "direct_response"


def test_script_like_request_uses_dedicated_script_first_route() -> None:
    interpreter, execute_turns = _build_interpreter()
    execute_turns.return_value = ToolCallingResult(final_text="脚本已执行并完成汇总", tool_calls=[])

    with patch("app.system.gateway.tool_calling_interpreter.exec_shell", return_value={"success": False}):
        command = interpreter.interpret(
            message="请遍历 app 目录并汇总 persistence 定义，如果太碎就先写脚本再执行",
            user_id="u1",
            session_id="sess-script",
            available_apps=[],
        )

    kwargs = execute_turns.call_args.kwargs
    assert kwargs["skill_id"] == "gateway_script_first_route"
    assert kwargs["max_turns"] == 4
    assert command.intent == "direct_response"



def test_script_like_request_exposes_only_script_first_tools_after_prestep_fallback() -> None:
    interpreter, execute_turns = _build_interpreter()
    registry = ToolRegistry()
    registry._tools = {}
    registry.register(ToolDefinition(name="exec_shell", description="", parameters=[]))
    registry.register(ToolDefinition(name="read_file", description="", parameters=[]))
    registry.register(ToolDefinition(name="write_file", description="", parameters=[]))
    registry.register(ToolDefinition(name="edit_file", description="", parameters=[]))
    registry.register(ToolDefinition(name="search_files", description="", parameters=[]))
    registry.register(ToolDefinition(name="query_asset_detail", description="", parameters=[]))
    interpreter._registry = registry
    execute_turns.return_value = ToolCallingResult(final_text="脚本已执行并完成汇总", tool_calls=[])

    with patch("app.system.gateway.tool_calling_interpreter.exec_shell", return_value={"success": False}):
        interpreter.interpret(
            message="请遍历 app 目录并批量提取 persistence 定义，再汇总结果",
            user_id="u1",
            session_id="sess-script-tools",
            available_apps=[],
        )

    kwargs = execute_turns.call_args.kwargs
    tool_names = [tool.name for tool in kwargs["tools"]]
    assert kwargs["skill_id"] == "gateway_script_first_route"
    assert tool_names == ["exec_shell", "read_file", "write_file", "edit_file", "ask_clarification", "unclear"]





def test_script_like_request_keeps_prompt_and_exec_tools_aligned_under_hot_tool_mode() -> None:
    interpreter, execute_turns = _build_interpreter()
    hot_tool_manager = MagicMock()
    hot_tool_manager.get_tools_for_session.return_value = [
        {"name": "exec_shell", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "read_file", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "write_file", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "edit_file", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "search_files", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "query_asset_detail", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
    ]
    interpreter._hot_tool_manager = hot_tool_manager
    execute_turns.return_value = ToolCallingResult(final_text="脚本已执行并完成汇总", tool_calls=[])

    with patch("app.system.gateway.tool_calling_interpreter.exec_shell", return_value={"success": False}):
        interpreter.interpret(
            message="请遍历 app 目录并批量提取 persistence 定义，再汇总结果",
            user_id="u1",
            session_id="sess-hot-script-tools",
            available_apps=[],
        )

    kwargs = execute_turns.call_args.kwargs
    exec_tool_names = [tool.name for tool in kwargs["tools"]]
    system_prompt = kwargs["system_prompt"]
    assert kwargs["skill_id"] == "gateway_script_first_route"
    assert exec_tool_names == ["exec_shell", "read_file", "write_file", "edit_file", "ask_clarification", "unclear"]
    assert "  • search_files:" not in system_prompt
    assert "  • query_asset_detail:" not in system_prompt
    for tool_name in exec_tool_names:
        assert f"  • {tool_name}:" in system_prompt



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
    assert kwargs["max_turns"] == 8
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




def test_process_result_builds_structured_answer_for_read_evidence() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(
        final_text="已读取 resource_center.py，其中 persistence_mode 默认值是 json。",
        tool_calls=[
            ToolCallRecord(
                tool_name="read_file",
                args={"path": "app/system/catalog/resource_center.py"},
                result={"success": True, "content": 'persistence_mode: str = "json"'},
            )
        ],
        evidence_items=[],
    )

    command = interpreter._process_result(result, "请读取代码并确认默认值")

    assert command.structured_answer is not None
    assert command.structured_answer.self_model.human_equivalence_state == "non_human_equivalent"
    assert command.structured_answer.self_model.capability_state == "tool_required"
    assert command.structured_answer.claim.text.startswith("已读取")


def test_process_result_marks_unverified_when_no_evidence_items() -> None:
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

    assert command.structured_answer is not None
    assert command.structured_answer.claim.evidence_grade == "none"
    assert command.structured_answer.unverified_points


def test_process_result_prefers_structured_json_payload_when_present() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(
        final_text=json.dumps({
            "claim": {"text": "已确认默认值是 json", "evidence_grade": "excerpt", "confidence": 0.92},
            "evidence": [{"grade": "excerpt", "source_type": "read_file", "source_ref": "app/system/catalog/resource_center.py", "snippet": "persistence_mode: str = \"json\""}],
            "unverified_points": ["尚未验证其他配置覆盖路径"],
        }, ensure_ascii=False),
        tool_calls=[
            ToolCallRecord(
                tool_name="read_file",
                args={"path": "app/system/catalog/resource_center.py"},
                result={"success": True, "content": 'persistence_mode: str = "json"'},
            )
        ],
    )

    command = interpreter._process_result(result, "请读取代码并确认默认值")

    assert command.structured_answer is not None
    assert command.structured_answer.claim.text == "已确认默认值是 json"
    assert command.structured_answer.claim.evidence_grade == "excerpt"
    assert command.structured_answer.unverified_points == ["尚未验证其他配置覆盖路径"]


def test_deterministic_prestep_telemetry_includes_profile_and_fallback_fields() -> None:
    interpreter, execute_turns = _build_interpreter()
    interpreter._telemetry_service = MagicMock()
    execute_turns.return_value = ToolCallingResult(final_text="已基于脚本结果完成汇总", tool_calls=[])
    with patch("app.system.gateway.tool_calling_interpreter.exec_shell", return_value={"success": True, "stdout": "[]"}):
        interpreter.interpret(
            message="请遍历 app 目录并检查 storage backend 和读写路径，再汇总结果",
            user_id="u1",
            session_id="sess-telemetry-extra",
            available_apps=[],
        )
    record = interpreter._telemetry_service.record_step.call_args.args[0]
    payload = record.payload_summary or {}
    assert payload["profile_hit"] is True
    assert "fallback_count" in payload
    assert "overreach_risk" in payload
    assert "verification_outcome" in payload


def test_build_structured_answer_falls_back_when_json_is_invalid() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(final_text='{"claim": ', tool_calls=[])

    command = interpreter._process_result(result, "请确认代码默认值")

    assert command.structured_answer is not None
    assert command.structured_answer.claim.text == '{"claim":'
    assert "结构化结果缺失或无效" in command.structured_answer.unverified_points[0]
    assert command.structured_answer.self_model.answer_mode == "verification_required"
    assert command.structured_answer.self_model.verification_mode == "required"


def test_build_structured_answer_normalizes_unknown_grade_and_clamps_confidence() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(
        final_text=json.dumps({
            "claim": {"text": "已得到一个不稳定结论", "evidence_grade": "weird", "confidence": 9},
            "evidence": [{"grade": "odd", "source_type": "read_file", "source_ref": "a.py", "snippet": "x=1"}],
            "unverified_points": [],
        }, ensure_ascii=False),
        tool_calls=[],
    )

    command = interpreter._process_result(result, "请确认代码默认值")

    assert command.structured_answer is not None
    assert command.structured_answer.claim.evidence_grade == "none"
    assert command.structured_answer.claim.confidence == 1.0
    assert command.structured_answer.evidence[0]["grade"] == "none"
    assert command.structured_answer.self_model.answer_mode == "verification_required"


def test_build_structured_answer_sets_tool_mode_for_excerpt_level_introspection() -> None:
    interpreter, _ = _build_interpreter()
    result = ToolCallingResult(
        final_text=json.dumps({
            "claim": {"text": "已确认默认值是 json", "evidence_grade": "excerpt", "confidence": 0.88},
            "evidence": [{"grade": "excerpt", "source_type": "read_file", "source_ref": "a.py", "snippet": "persistence_mode='json'"}],
            "unverified_points": ["尚未验证环境覆盖"],
        }, ensure_ascii=False),
        tool_calls=[],
    )

    command = interpreter._process_result(result, "请确认代码默认值")

    assert command.structured_answer is not None
    assert command.structured_answer.self_model.answer_mode == "tool_required"
    assert command.structured_answer.self_model.verification_mode == "light"
