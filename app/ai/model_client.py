from __future__ import annotations

import logging
import time
import yaml
from pathlib import Path

import json
from typing import Any

import httpx

from app.models.model_config import ModelConfig

logger = logging.getLogger(__name__)


class ModelClientError(ValueError):
    def __init__(self, message: str, status_code: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _build_timeout(timeout_seconds: float) -> httpx.Timeout:
    return httpx.Timeout(
        connect=min(30.0, timeout_seconds),
        read=timeout_seconds,
        write=min(30.0, timeout_seconds),
        pool=min(30.0, timeout_seconds),
    )


def _safe_json(response: httpx.Response) -> dict:
    content_type = (response.headers.get("content-type", "") or "").lower()
    body_preview = response.text[:300]
    if not body_preview.strip():
        raise ModelClientError(
            "LLM returned empty response body",
            status_code=response.status_code,
            retryable=response.status_code >= 500,
        )
    if "application/json" not in content_type:
        raise ModelClientError(
            f"LLM returned non-JSON response: {content_type or 'unknown'} {body_preview}",
            status_code=response.status_code,
            retryable=response.status_code >= 500,
        )
    try:
        data = response.json()
    except json.JSONDecodeError:
        raise ModelClientError(
            f"LLM returned invalid JSON: {body_preview}",
            status_code=response.status_code,
            retryable=response.status_code >= 500,
        )
    if not isinstance(data, dict):
        raise ModelClientError(
            f"LLM returned unexpected JSON shape: {type(data).__name__}",
            status_code=response.status_code,
            retryable=response.status_code >= 500,
        )
    return data


def _parse_sse_json_text(raw_text: str) -> dict:
    chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    finish_reason = "stop"
    for line in raw_text.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        choice0 = choices[0] or {}
        delta = choice0.get("delta") or {}
        finish_reason = choice0.get("finish_reason") or finish_reason
        content = delta.get("content")
        if isinstance(content, str) and content:
            chunks.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text_part = item.get("text")
                    if isinstance(text_part, str) and text_part:
                        chunks.append(text_part)
        tc = delta.get("tool_calls")
        if isinstance(tc, list):
            tool_calls.extend(x for x in tc if isinstance(x, dict))
    text = "".join(chunks)
    return {
        "choices": [{"message": {"content": text, "tool_calls": tool_calls}, "finish_reason": finish_reason}],
        "usage": {},
    }


def _safe_chat_completion_payload(response: httpx.Response) -> dict:
    content_type = (response.headers.get("content-type", "") or "").lower()
    if "application/json" in content_type:
        return _safe_json(response)
    if "text/event-stream" in content_type:
        return _parse_sse_json_text(response.text)
    body_preview = response.text[:300]
    raise ModelClientError(
        f"LLM returned unsupported response type: {content_type or 'unknown'} {body_preview}",
        status_code=response.status_code,
        retryable=response.status_code >= 500,
    )


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
        try:
            with httpx.Client(timeout=self._config.timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.ReadTimeout as e:
            raise ModelClientError(
                f"LLM request read timed out after {self._config.timeout_seconds}s",
                status_code=None,
                retryable=True,
            ) from e
        except Exception as e:
            raise ModelClientError(f"LLM request failed: {str(e)}", status_code=None, retryable=False) from e
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
        # Handle base_url that may or may not end with /v1
        base = self._config.base_url.rstrip("/")
        if base.endswith("/v1"):
            url = base + "/chat/completions"
        else:
            url = base + "/v1/chat/completions"
        payload: dict = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            if not stream:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code >= 400:
                    body = response.text[:300]
                    raise ModelClientError(
                        f"Chat request failed: {response.status_code} {body}",
                        status_code=response.status_code,
                        retryable=response.status_code >= 500,
                    )
                data = _safe_json(response)
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                usage = data.get("usage", {}) or {}
                return text, {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "model": model_name,
                }
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
        # Handle base_url that may or may not end with /v1
        base = self._config.base_url.rstrip("/")
        if base.endswith("/v1"):
            url = base + "/chat/completions"
        else:
            url = base + "/v1/chat/completions"
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
            tool_names = [tool.get("function", {}).get("name") for tool in tools]
            logger.info(
                "ModelClient.chat_with_tools model=%s tool_names=%s message_count=%s",
                model_name,
                tool_names,
                len(messages),
            )
            last_error: Exception | None = None
            max_attempts = 4
            transient_statuses = {502, 503, 504}
            for attempt in range(max_attempts):
                try:
                    response = client.post(url, json=payload, headers=headers)
                    if response.status_code in transient_statuses and attempt < max_attempts - 1:
                        wait_seconds = 1.5 * (attempt + 1)
                        logger.warning(
                            "ModelClient.chat_with_tools transient server failure model=%s attempt=%s status=%s retry_in=%ss",
                            model_name,
                            attempt + 1,
                            response.status_code,
                            wait_seconds,
                        )
                        time.sleep(wait_seconds)
                        continue
                    if response.status_code >= 500 and attempt < max_attempts - 1:
                        wait_seconds = 0.75 * (attempt + 1)
                        logger.warning(
                            "ModelClient.chat_with_tools transient server failure model=%s attempt=%s status=%s retry_in=%ss",
                            model_name,
                            attempt + 1,
                            response.status_code,
                            wait_seconds,
                        )
                        time.sleep(wait_seconds)
                        continue
                    break
                except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ReadError) as exc:
                    last_error = exc
                    if attempt >= max_attempts - 1:
                        raise ModelClientError(
                            f"Chat with tools transport failed after retry: {exc}",
                            status_code=None,
                            retryable=True,
                        ) from exc
                    wait_seconds = 0.75 * (attempt + 1)
                    logger.warning(
                        "ModelClient.chat_with_tools transient transport failure model=%s attempt=%s error=%s retry_in=%ss",
                        model_name,
                        attempt + 1,
                        exc,
                        wait_seconds,
                    )
                    time.sleep(wait_seconds)
            else:
                raise ModelClientError(
                    f"Chat with tools transport failed: {last_error}",
                    status_code=None,
                    retryable=True,
                )
        if response.status_code >= 400:
            debug_path = Path('/tmp/agentsystem_chat_with_tools_payload.json')
            try:
                debug_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass
            raise ModelClientError(
                f"Chat with tools failed: {response.status_code} {response.text[:300]} | payload_dump={debug_path}",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )
        data = _safe_chat_completion_payload(response)
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})
        text = message.get("content", "") or ""
        tool_calls = message.get("tool_calls", [])
        logger.info(
            "ModelClient.chat_with_tools response model=%s returned_tool_calls=%s finish_reason=%s",
            model_name,
            [tc.get("function", {}).get("name") for tc in tool_calls],
            choice.get("finish_reason", ""),
        )

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
        max_turns: int = 100,
    ) -> tuple[str, dict]:
        """Multi-turn tool calling loop.
        Load max_turns from global config if not provided.

        1. Send system + user + tools -> LLM
        2. If tool_calls -> execute -> loop
        3. Until LLM gives final text answer
        """
        if max_turns is None:
            try:
                from app.ai.model_config_loader import DEFAULT_MODEL_CONFIG_PATH
                cfg = yaml.safe_load(DEFAULT_MODEL_CONFIG_PATH.read_text(encoding="utf-8")) or {}
                app_cfg = cfg.get("app", {}) or {}
                max_turns = app_cfg.get("max_turns", 10)
            except Exception:
                max_turns = 10

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

            assistant_message = {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

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
        """Convenience: system + user message -> assistant text and usage."""
        return self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
