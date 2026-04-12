"""LLM Responder — generates contextual replies using the remote model.

Phase 8.2: bridges rule-based intent parsing with LLM-powered response generation.
Phase E.2: tool-aware intent parsing and reply generation with tool context.
Falls back to rule-based replies when the model is unavailable.
"""

from __future__ import annotations

import json
from typing import Any

from app.models.chat import ChatMessageResponse, ActionSuggestion, TokenUsage
from app.services.model_config_loader import ModelConfigLoader, ModelConfigError
from app.services.model_client import OpenAIResponsesClient, ModelClientError
from app.services.model_router import ModelRouter
from app.services.tool_registry import ToolRegistry


class LLMResponderError(Exception):
    pass


class LLMResponder:
    """Uses the remote LLM to generate contextual replies."""

    def __init__(
        self,
        model_client: OpenAIResponsesClient | None = None,
        model_router: ModelRouter | None = None,
    ) -> None:
        self._model_router = model_router
        if model_client:
            self._client = model_client
            self._available = True
        elif model_router:
            try:
                self._client = model_router.get_client("llm_responder")
                self._available = True
            except Exception:
                self._client = None
                self._available = False
        else:
            try:
                loader = ModelConfigLoader()
                config = loader.load()
                api_key = loader.resolve_api_key(config)
                self._client = OpenAIResponsesClient(config=config, api_key=api_key)
                self._available = True
            except (ModelConfigError, Exception):
                self._client = None
                self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def generate_reply(
        self,
        system_context: str,
        user_message: str,
        *,
        app_context: list[dict[str, Any]] | None = None,
        tool_registry: "ToolRegistry | None" = None,
        executed_tool: str | None = None,
        tool_result: str | None = None,
        max_tokens: int = 500,
    ) -> tuple[str | None, TokenUsage | None]:
        """Generate a contextual reply using the LLM.

        Args:
            system_context: Base system context (identity, role).
            user_message: User's original message.
            app_context: Available apps list.
            tool_registry: Tool registry — injects tool awareness into prompt.
            executed_tool: Name of the tool that was just executed.
            tool_result: Result text from the executed tool.
            max_tokens: Max completion tokens.

        Returns (text, usage) tuple. Text is None if the model is unavailable.
        """
        if not self._available or not self._client:
            return None, None

        try:
            sys_prompt = (
                f"{system_context}\n\n"
                "Reply in Chinese. Be concise and helpful. "
                "Do NOT use markdown formatting — use plain text with emoji. "
                "Keep responses under 200 characters unless the user asks for details."
            )

            # Phase E.2: Inject tool awareness
            if tool_registry:
                tool_text = tool_registry.to_prompt_text(include_descriptions=True)
                sys_prompt += f"\n\n{tool_text}"
                sys_prompt += (
                    "\n\n## 回复规则\n"
                    "1. 如果用户意图匹配上述某个工具，告知用户你执行了该工具，并汇报结果\n"
                    "2. 如果工具已经执行，根据 tool_result 生成友好的自然语言回复\n"
                    "3. 如果用户询问能力，基于工具列表回答\n"
                    "4. 不要编造不存在的工具或能力"
                )

            if app_context:
                app_list = ", ".join(
                    f"{a.get('name', '?')}({a.get('status', '?')})" for a in app_context
                )
                sys_prompt += f"\n\n当前已安装 App: {app_list}"

            # If a tool was executed, provide its result
            if executed_tool and tool_result:
                sys_prompt += f"\n\n## 已执行工具: {executed_tool}\n工具返回结果:\n{tool_result}"
                sys_prompt += "\n\n请基于以上结果生成友好的中文回复。"

            text, usage = self._client.generate_response(
                system_prompt=sys_prompt,
                user_message=user_message,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return text, TokenUsage(**usage) if usage else None
        except (ModelClientError, Exception):
            return None, None

    def parse_intent(self, user_message: str, available_apps: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any] | None, TokenUsage | None]:
        """Ask the LLM to parse user intent into a structured command.

        Returns (parsed_dict, usage) tuple. Dict is None if parsing fails.
        """
        if not self._available or not self._client:
            return None, None

        try:
            app_info = ""
            if available_apps:
                app_info = "\nAvailable apps: " + json.dumps(
                    [{"name": a["name"], "status": a["status"]} for a in available_apps],
                    ensure_ascii=False,
                )

            sys_prompt = (
                "You are an intent parser for an App OS system. "
                "Analyze the user message and return a JSON object with these fields:\n"
                '- "intent": one of [greet, list_apps, create_app, start_app, stop_app, '
                'pause_app, resume_app, query_app, modify_app, delete_app, query_status, query_help, unclear]\n'
                '- "target_app": app name if applicable, null otherwise\n'
                '- "parameters": object with extracted params (app_type, schedule_type, '
                'schedule_interval, schedule_cron, threshold, modification, etc.)\n'
                '- "confidence": float 0.0-1.0\n'
                '- "requires_clarification": boolean\n'
                "Return ONLY valid JSON, no extra text."
                f"{app_info}"
            )

            result, usage = self._client.generate_response(
                system_prompt=sys_prompt,
                user_message=user_message,
                max_tokens=300,
                temperature=0.1,
            )

            if result:
                # Try to extract JSON from the response
                result = result.strip()
                if result.startswith("```"):
                    # Strip markdown code blocks
                    lines = result.split("\n")
                    result = "\n".join(lines[1:-1])
                return json.loads(result), usage
        except (ModelClientError, json.JSONDecodeError, Exception):
            return None, None

    def parse_intent_with_tools(
        self,
        user_message: str,
        tool_registry: "ToolRegistry",
        available_apps: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any] | None, TokenUsage | None]:
        """Ask the LLM to parse user intent using tool registry context.

        The LLM receives the full tool registry and selects the best matching tool.
        Returns (parsed_dict, usage) tuple.

        parsed_dict format:
        {
            "intent": "tool_name",
            "target_app": "app_name" or null,
            "parameters": {...},
            "confidence": 0.0-1.0,
            "requires_clarification": bool
        }
        """
        if not self._available or not self._client:
            return None, None

        try:
            # Build tool context from registry
            tool_list = tool_registry.to_prompt_text(include_descriptions=True)

            # Build available apps info
            app_info = ""
            if available_apps:
                app_info = "\n当前已安装 App: " + ", ".join(
                    f"{a.get('name', '?')}({a.get('status', '?')})" for a in available_apps
                )

            sys_prompt = (
                f"你是一个意图解析器，负责分析用户的自然语言消息并选择最合适的工具来执行。\n\n"
                f"{tool_list}"
                f"{app_info}\n\n"
                "分析用户消息，返回 JSON 对象：\n"
                '- "intent": 最匹配的工具名称（从上面的列表中选择），如果不确定用 "unclear"\n'
                '- "target_app": 如果涉及具体 App，填写 App 名称，否则 null\n'
                '- "parameters": 从消息中提取的参数对象\n'
                '- "confidence": 置信度 0.0-1.0\n'
                '- "requires_clarification": 是否需要用户澄清（布尔值）\n'
                "只返回有效 JSON，不要包含其他文字。"
            )

            result, usage = self._client.generate_response(
                system_prompt=sys_prompt,
                user_message=user_message,
                max_tokens=300,
                temperature=0.1,
            )

            if result:
                result = result.strip()
                if result.startswith("```"):
                    lines = result.split("\n")
                    result = "\n".join(lines[1:-1])
                return json.loads(result), usage
        except (ModelClientError, json.JSONDecodeError, Exception):
            return None, None

