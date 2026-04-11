"""LLM Responder — generates contextual replies using the remote model.

Phase 8.2: bridges rule-based intent parsing with LLM-powered response generation.
Falls back to rule-based replies when the model is unavailable.
"""

from __future__ import annotations

import json
from typing import Any

from app.models.chat import ChatMessageResponse, ActionSuggestion, TokenUsage
from app.services.model_config_loader import ModelConfigLoader, ModelConfigError
from app.services.model_client import OpenAIResponsesClient, ModelClientError


class LLMResponderError(Exception):
    pass


class LLMResponder:
    """Uses the remote LLM to generate contextual replies."""

    def __init__(self, model_client: OpenAIResponsesClient | None = None) -> None:
        if model_client:
            self._client = model_client
            self._available = True
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
        max_tokens: int = 500,
    ) -> tuple[str | None, TokenUsage | None]:
        """Generate a contextual reply using the LLM.

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

            if app_context:
                app_list = ", ".join(
                    f"{a.get('name', '?')}({a.get('status', '?')})" for a in app_context
                )
                sys_prompt += f"\n\nCurrent Apps: {app_list}"

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
