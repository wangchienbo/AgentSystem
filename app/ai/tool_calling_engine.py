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
        max_turns=10,
    )
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.model_router import ModelRouter, ModelRouterError
from app.services.model_client import OpenAIResponsesClient, ModelClientError


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
class ToolCallingResult:
    """Result of a multi-turn tool calling session."""
    final_text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    turns: int = 0
    truncated: bool = False
    usage: dict[str, Any] = field(default_factory=dict)


class ToolCallingEngineError(ValueError):
    pass


class ToolCallingEngine:
    """Multi-turn tool calling engine with model routing."""

    def __init__(self, model_router: ModelRouter) -> None:
        self._router = model_router
        self._tools: dict[str, Callable] = {}

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
        max_turns: int = 10,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model_override: str | None = None,
        asset_id: str | None = None,  # Caller asset context for model routing
    ) -> ToolCallingResult:
        """Execute multi-turn tool calling.

        Args:
            skill_id: Skill identifier (used for model routing)
            system_prompt: System prompt
            user_message: User message
            tools: List of tool definitions
            max_turns: Maximum tool calling rounds
            temperature: LLM temperature
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
        
        if model_override:
            caller = "override"
            client = self._get_client_by_name(model_override)
        else:
            client = self._router.get_client(caller)

        # Build tool definitions
        tool_defs = [t.to_openai_format() for t in tools]

        # Build tool handlers map
        handlers: dict[str, Callable] = {}
        for t in tools:
            if t.name in self._tools:
                handlers[t.name] = self._tools[t.name]

        # Execute multi-turn loop
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
        model_name = model_override or client._config.model

        for turn in range(max_turns):
            response, usage = client.chat_with_tools(
                messages=messages,
                tools=tool_defs,
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_usage["total_tokens"] += usage.get("total_tokens", 0)

            message = response["message"]
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                total_usage["model"] = model_name
                total_usage["turns"] = turn + 1
                return ToolCallingResult(
                    final_text=response.get("text", ""),
                    tool_calls=call_records,
                    turns=turn + 1,
                    usage=total_usage,
                )

            messages.append(message)

            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                tool_args_str = tc.get("function", {}).get("arguments", "{}")
                tool_call_id = tc.get("id", "")

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                handler = handlers.get(tool_name)
                if handler:
                    try:
                        result = handler(**tool_args) if isinstance(tool_args, dict) else handler(tool_args)
                        result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                        call_records.append(ToolCallRecord(tool_name=tool_name, args=tool_args, result=result))
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)}, ensure_ascii=False)
                        call_records.append(ToolCallRecord(tool_name=tool_name, args=tool_args, result=None, error=str(e)))
                else:
                    result_str = json.dumps({"error": f"Tool not found: {tool_name}"}, ensure_ascii=False)
                    call_records.append(ToolCallRecord(tool_name=tool_name, args=tool_args, result=None, error="Tool not found"))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_str,
                })

        total_usage["model"] = model_name
        total_usage["turns"] = max_turns
        total_usage["truncated"] = True
        return ToolCallingResult(
            final_text=f"[Reached max turns ({max_turns})]",
            tool_calls=call_records,
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
            raise ToolCallingEngineError("Missing API key in config or environment")
        return OpenAIResponsesClient(config=config, api_key=api_key)
