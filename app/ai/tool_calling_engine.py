"""Native Tool Calling Engine — multi-turn LLM + tool execution loop.

Provides a high-level interface for skills to perform iterative analysis:
1. LLM decides which tool(s) to call
2. Engine executes tools
3. Results fed back to LLM
4. Loop until LLM produces final answer

Usage:
    engine = ToolCallingEngine(model_router)
    
    # Register tools
    engine.register_tool("query_metrics", query_metrics_handler)
    engine.register_tool("get_history", get_history_handler)
    
    # Execute multi-turn analysis
    result, usage = engine.execute_turns(
        skill_id="monitoring-skill",
        system_prompt="你是监控分析助手...",
        user_message="CPU 使用率异常",
        tools=[...],  # tool definitions
        max_turns=30,
    )
"""
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import json
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable


MAX_TOOL_RESULT_CHARS = 800

from app.services.model_router import ModelRouter, ModelRouterError
from app.services.model_client import OpenAIResponsesClient, ModelClientError


NON_CONVERGENCE_TEXT = "当前工具链路未在限定时间内收敛。我先给你保守结论: 需要轻量验证，或改走更窄的探针继续确认。"
from app.models.telemetry import StepTelemetryRecord


@dataclass
class ToolDef:
    """Tool definition for OpenAI function calling format."""
    name: str
    description: str
    parameters: dict  # JSON Schema for tool arguments

    def to_openai_format(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCallRecord:
    """Record of a single tool call."""
    tool_name: str
    args: dict
    result: Any
    error: str = ""


@dataclass
class EvidenceItem:
    """Structured evidence item for answer-governance use."""
    grade: str
    source_type: str
    source_ref: str = ""
    snippet: str = ""
    truncated: bool = False
    scope: str = "mixed"
    supports_claims: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallingResult:
    """Result of a multi-turn tool calling session."""
    final_text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    turns: int = 0
    truncated: bool = False
    usage: dict[str, Any] = field(default_factory=dict)


class ToolCallingEngineError(ValueError):
    pass


class ToolCallingEngine:
    """Multi-turn tool calling engine with model routing."""

    def __init__(self, model_router: ModelRouter, telemetry_service: Any | None = None) -> None:
        self._router = model_router
        self._tools: dict[str, Callable] = {}
        self._telemetry_service = telemetry_service

    def _sanitize_tool_result(self, tool_name: str, result: Any) -> str:
        """Compress tool result into a bounded payload for the next LLM turn."""
        if isinstance(result, str):
            return result[:MAX_TOOL_RESULT_CHARS]

        encoded = json.dumps(result, ensure_ascii=False)
        return encoded[:MAX_TOOL_RESULT_CHARS]

    def _build_evidence_items(self, tool_name: str, result: Any) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        if tool_name == "read_file" and isinstance(result, dict) and result.get("success"):
            content = str(result.get("content", ""))
            items.append(EvidenceItem(
                grade="excerpt",
                source_type="read_file",
                source_ref=str(result.get("path", "") or ""),
                snippet=content[:300],
                truncated=len(content) > 300,
                scope="static_code",
                supports_claims=["implementation_detail", "default_value", "config_fact"],
            ))
        elif tool_name == "search_files" and isinstance(result, dict):
            results = result.get("results", []) or []
            if results:
                first = results[0]
                items.append(EvidenceItem(
                    grade="hint",
                    source_type="search_files",
                    source_ref=str(first.get("file", "") or ""),
                    snippet=json.dumps(first, ensure_ascii=False)[:300],
                    truncated=False,
                    scope="static_code",
                    supports_claims=["candidate_location"],
                    metadata={"match_count": len(results)},
                ))
        elif tool_name == "exec_shell" and result is not None:
            encoded = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            items.append(EvidenceItem(
                grade="runtime_observation",
                source_type="exec_shell",
                source_ref="local_command",
                snippet=encoded[:300],
                truncated=len(encoded) > 300,
                scope="runtime_state",
                supports_claims=["runtime_observation", "script_output"],
            ))
        return items

    def register_tool(self, name: str, handler: Callable) -> None:
        """Register a tool that LLM can call."""
        self._tools[name] = handler

    def register_tools(self, tools: dict[str, Callable]) -> None:
        """Register multiple tools at once."""
        self._tools.update(tools)

    def execute_turns(
        self,
        skill_id: str,
        system_prompt: str,
        user_message: str,
        tools: list[ToolDef],
        max_turns: int | None = None,  # None means read from global config
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model_override: str | None = None,
        asset_id: str | None = None,  # Caller asset context for model routing
        session_id: str | None = None,
        user_id: str | None = None,
        interaction_id: str | None = None,
    ) -> ToolCallingResult:
        """Execute multi-turn tool calling.

        Args:
            skill_id: Skill identifier (used for model routing)
            system_prompt: System prompt
            user_message: User message
            tools: List of tool definitionstemperature: LLM temperature
            max_tokens: Max tokens per turn
            model_override: Override model (bypasses router)
            asset_id: Caller asset ID for asset-level model configuration

        Returns:
            ToolCallingResult with final text and call records
        """
        # Build caller identifier with asset context if available
        if asset_id:
            caller = f"asset:{asset_id}:skill:{skill_id}"
        else:
            caller = f"skill:{skill_id}"

        logger.debug(f"ToolCallingEngine: getting client for caller={caller}, model_override={model_override}")
        
        if model_override:
            caller = "override"
            client = self._get_client_by_name(model_override)
        else:
            client = self._router.get_client(caller)
            
        logger.debug(f"ToolCallingEngine: client type={type(client).__name__}, client={client}")

        # Build tool definitions
        tool_defs = [t.to_openai_format() for t in tools]

        # Build tool handlers map
        handlers: dict[str, Callable] = {}
        for t in tools:
            if t.name in self._tools:
                handlers[t.name] = self._tools[t.name]

        logger.info(
            "ToolCallingEngine input skill=%s asset=%s session=%s tools=%s handlers=%s",
            skill_id,
            asset_id,
            session_id,
            [t.name for t in tools],
            sorted(handlers.keys()),
        )

        # Execute multi-turn loop
        # NOTE: Some upstream chat_with_tools providers reject replaying prior
        # assistant/tool call history in OpenAI tool-call shape. To maximize
        # compatibility, keep only the current system+user turn for each tool
        # selection cycle in this gateway path.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        total_usage: dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        call_records: list[ToolCallRecord] = []
        evidence_items: list[EvidenceItem] = []
        model_name = model_override or client._config.model
        interaction_id = interaction_id or f"toolcall:{session_id or 'unknown'}:{skill_id}:{abs(hash(user_message))}"

        if max_turns is None:
            max_turns = 8

        consecutive_tool_name = None
        consecutive_tool_count = 0

        for turn in range(max_turns):
            logger.info(
                "ToolCallingEngine turn=%s session=%s payload_tools=%s",
                turn + 1,
                session_id,
                [tool.get("function", {}).get("name") for tool in tool_defs],
            )
            try:
                response, usage = client.chat_with_tools(
                    messages=messages,
                    tools=tool_defs,
                    model=model_name,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except ModelClientError as exc:
                if turn == 0 and getattr(exc, "retryable", False):
                    logger.warning(
                        "ToolCallingEngine degraded non-convergent tool route session=%s turn=%s error=%s",
                        session_id,
                        turn + 1,
                        exc,
                    )
                    total_usage["model"] = model_name
                    total_usage["turns"] = turn + 1
                    total_usage["degraded"] = True
                    total_usage["degraded_reason"] = "tool_route_retryable_failure"
                    return ToolCallingResult(
                        final_text=NON_CONVERGENCE_TEXT,
                        tool_calls=call_records,
                        evidence_items=evidence_items,
                        turns=turn + 1,
                        truncated=False,
                        usage=total_usage,
                    )
                raise
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_usage["total_tokens"] += usage.get("total_tokens", 0)

            message = response["message"]
            raw_tool_calls = response.get("tool_calls", [])
            tool_calls = [
                tc for tc in raw_tool_calls
                if isinstance(tc, dict)
                and tc.get("function", {}).get("name")
                and tc.get("id")
            ]
            if raw_tool_calls and len(tool_calls) != len(raw_tool_calls):
                logger.warning(
                    "ToolCallingEngine filtered malformed tool calls: raw=%s filtered=%s session=%s",
                    [tc.get("function", {}).get("name") if isinstance(tc, dict) else None for tc in raw_tool_calls],
                    [tc.get("function", {}).get("name") for tc in tool_calls],
                    session_id,
                )

            if not tool_calls:
                if self._telemetry_service is not None:
                    self._telemetry_service.record_step(
                        StepTelemetryRecord(
                            interaction_id=interaction_id,
                            step_id=f"llm_turn_{turn + 1}",
                            step_type="reason",
                            name="llm_final_response",
                            input_tokens=usage.get("prompt_tokens", 0),
                            output_tokens=usage.get("completion_tokens", 0),
                            success=True,
                            payload_summary={
                                "turn": turn + 1,
                                "termination_reason": "final_response",
                                "session_id": session_id,
                                "user_id": user_id,
                            },
                        ),
                        app_id=asset_id,
                    )
                total_usage["model"] = model_name
                total_usage["turns"] = turn + 1
                return ToolCallingResult(
                    final_text=response.get("text", ""),
                    tool_calls=call_records,
                    evidence_items=evidence_items,
                    turns=turn + 1,
                    usage=total_usage,
                )

            assistant_message = {"role": "assistant"}
            assistant_content = message.get("content")
            if assistant_content is not None:
                assistant_message["content"] = assistant_content
            else:
                assistant_message["content"] = None
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)

            for tc in tool_calls[:1]:
                tool_name = tc.get("function", {}).get("name", "")
                tool_args_str = tc.get("function", {}).get("arguments", "{}")
                tool_call_id = tc.get("id", "")

                if tool_name == consecutive_tool_name:
                    consecutive_tool_count += 1
                else:
                    consecutive_tool_name = tool_name
                    consecutive_tool_count = 1

                if tool_name == "call_asset_method" and consecutive_tool_count >= 3:
                    logger.warning(
                        "ToolCallingEngine loop guard triggered session=%s turn=%s tool=%s consecutive=%s",
                        session_id,
                        turn + 1,
                        tool_name,
                        consecutive_tool_count,
                    )
                    guard_result = (
                        "[loop-guard] 已连续多次调用 call_asset_method。"
                        "如果现有资产结果已经足够，请立即停止工具调用并直接回答；"
                        "只有在缺少明确关键事实时，才允许再补一次调用。"
                    )
                    call_records.append(ToolCallRecord(tool_name=tool_name, args={"loop_guard": True}, result=guard_result))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": guard_result,
                    })
                    break

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                if not tool_name:
                    call_records.append(ToolCallRecord(tool_name="", args=tool_args, result=None, error="Empty tool name"))
                    continue

                handler = handlers.get(tool_name)
                if handler:
                    try:
                        result = handler(**tool_args) if isinstance(tool_args, dict) else handler(tool_args)
                        result_str = self._sanitize_tool_result(tool_name, result)
                        call_records.append(ToolCallRecord(tool_name=tool_name, args=tool_args, result=result))
                        evidence_items.extend(self._build_evidence_items(tool_name, result))
                        if self._telemetry_service is not None:
                            self._telemetry_service.record_step(
                                StepTelemetryRecord(
                                    interaction_id=interaction_id,
                                    step_id=f"tool_{turn + 1}_{len(call_records)}",
                                    step_type="tool",
                                    name=tool_name,
                                    success=True,
                                    payload_summary={
                                        "turn": turn + 1,
                                        "tool_name": tool_name,
                                        "args": tool_args,
                                        "session_id": session_id,
                                        "user_id": user_id,
                                    },
                                ),
                                app_id=asset_id,
                            )
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)}, ensure_ascii=False)
                        call_records.append(ToolCallRecord(tool_name=tool_name, args=tool_args, result=None, error=str(e)))
                        if self._telemetry_service is not None:
                            self._telemetry_service.record_step(
                                StepTelemetryRecord(
                                    interaction_id=interaction_id,
                                    step_id=f"tool_{turn + 1}_{len(call_records)}",
                                    step_type="tool",
                                    name=tool_name,
                                    success=False,
                                    error_code="tool_execution_error",
                                    payload_summary={
                                        "turn": turn + 1,
                                        "tool_name": tool_name,
                                        "args": tool_args,
                                        "error": str(e),
                                        "session_id": session_id,
                                        "user_id": user_id,
                                    },
                                ),
                                app_id=asset_id,
                            )
                else:
                    result_str = json.dumps({"error": f"Tool not found: {tool_name}"}, ensure_ascii=False)
                    call_records.append(ToolCallRecord(tool_name=tool_name, args=tool_args, result=None, error="Tool not found"))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_str,
                })


        if self._telemetry_service is not None:
            self._telemetry_service.record_step(
                StepTelemetryRecord(
                    interaction_id=interaction_id,
                    step_id=f"llm_truncated_{max_turns}",
                    step_type="reason",
                    name="max_turns_reached",
                    success=False,
                    error_code="max_turns_reached",
                    payload_summary={
                        "max_turns": max_turns,
                        "session_id": session_id,
                        "user_id": user_id,
                    },
                ),
                app_id=asset_id,
            )
        total_usage["model"] = model_name
        total_usage["turns"] = max_turns
        total_usage["truncated"] = True
        return ToolCallingResult(
            final_text=f"[Reached max turns ({max_turns})]",
            tool_calls=call_records,
            evidence_items=evidence_items,
            turns=max_turns,
            truncated=True,
            usage=total_usage,
        )

    def _get_client_by_name(self, model_name: str) -> OpenAIResponsesClient:
        """Create client with a specific model name."""
        from app.models.model_config import ModelConfig
        config = ModelConfig(
            base_url="https://crs.ruinique.com/v1",
            model=model_name,
            api_key_env="OPENAI_API_KEY",
        )
        # Prioritize config file API key over environment variable
        api_key = getattr(self._router, '_fallback_api_key', None)
        if not api_key:
            import os
            api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ToolCallingEngineError("Missing OPENAI_API_KEY in config or environment")
        return OpenAIResponsesClient(config=config, api_key=api_key)
