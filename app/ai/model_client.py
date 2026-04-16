from __future__ import annotations

import json
from typing import Any

import httpx

from app.models.model_config import ModelConfig


class ModelClientError(ValueError):
    def __init__(self, message: str, status_code: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class OpenAIResponsesClient:
    def __init__(self, config: ModelConfig, api_key: str) -> None:
        self._config = config
        self._api_key = api_key

    def request(self, input_payload, *, extra_payload: dict | None = None) -> dict:
        url = self._config.base_url.rstrip("/") + "/v1/responses"
        payload = {
            "model": self._config.model,
            "input": input_payload,
        }
        if extra_payload:
            payload.update(extra_payload)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            response = client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise ModelClientError(
                f"Model probe failed: {response.status_code} {response.text[:300]}",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )
        content_type = response.headers.get("content-type", "")
        normalized = content_type.lower()
        if "application/json" in normalized:
            return response.json()
        if "text/event-stream" in normalized:
            return {
                "status_code": response.status_code,
                "content_type": content_type,
                "stream_preview": response.text[:500],
            }
        return {
            "status_code": response.status_code,
            "content_type": content_type,
            "body_preview": response.text[:500],
        }

    def probe(self, prompt: str = "ping") -> dict:
        return self.request(prompt)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        stream: bool = True,
    ) -> tuple[str, dict]:
        """Send a chat completion request and return the assistant's text response."""
        model_name = model or self._config.model
        url = self._config.base_url.rstrip("/") + "/v1/chat/completions"
        payload: dict = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    body = response.read().decode(errors="replace")[:300]
                    raise ModelClientError(
                        f"Chat request failed: {response.status_code} {body}",
                        status_code=response.status_code,
                        retryable=response.status_code >= 500,
                    )
                content_parts: list[str] = []
                prompt_tokens = 0
                completion_tokens = 0
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            content_parts.append(delta["content"])
                        usage = chunk.get("usage", {})
                        if usage:
                            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                            completion_tokens = usage.get("completion_tokens", completion_tokens)
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue
                if prompt_tokens == 0 and completion_tokens == 0:
                    full_text = "".join(content_parts)
                    prompt_tokens = sum(len(m.get("content", "")) for m in messages) // 4
                    completion_tokens = len(full_text) // 4
        return "".join(content_parts), {"model": model_name, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens}

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> tuple[dict, dict]:
        """Chat completion with native tool calling.

        Uses /v1/chat/completions with tools parameter (non-streaming for reliable parsing).
        Returns (response_dict, usage_info).
        """
        model_name = model or self._config.model
        url = self._config.base_url.rstrip("/") + "/v1/chat/completions"
        payload: dict = {
            "model": model_name,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            response = client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise ModelClientError(
                f"Chat with tools failed: {response.status_code} {response.text[:300]}",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )
        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})
        text = message.get("content", "") or ""
        tool_calls = message.get("tool_calls", [])

        return {
            "message": message,
            "text": text,
            "tool_calls": tool_calls,
            "finish_reason": choice.get("finish_reason", ""),
        }, {
            "model": model_name,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }

    def chat_turns(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]],
        tool_handlers: dict[str, Any],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        max_turns: int = 10,
    ) -> tuple[str, dict]:
        """Multi-turn tool calling loop.

        1. Send system + user + tools → LLM
        2. If tool_calls → execute → loop
        3. Until LLM gives final text answer
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        total_usage: dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        model_name = model or self._config.model

        for turn in range(max_turns):
            response, usage = self.chat_with_tools(
                messages=messages,
                tools=tools,
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
                return response.get("text", ""), total_usage

            messages.append(message)

            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                tool_args_str = tc.get("function", {}).get("arguments", "{}")
                tool_call_id = tc.get("id", "")

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                handler = tool_handlers.get(tool_name)
                if handler:
                    try:
                        result = handler(**tool_args) if isinstance(tool_args, dict) else handler(tool_args)
                        result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)}, ensure_ascii=False)
                else:
                    result_str = json.dumps({"error": f"Tool not found: {tool_name}"}, ensure_ascii=False)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_str,
                })

        total_usage["model"] = model_name
        total_usage["turns"] = max_turns
        total_usage["truncated"] = True
        return f"[Reached max turns ({max_turns})]", total_usage

    def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        *,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> tuple[str, dict]:
        """Convenience: system + user message → assistant text and usage."""
        return self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
