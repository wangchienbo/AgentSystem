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
    tool_call_map: dict[int, dict[str, Any]] = {}
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
            for item in tc:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index", 0)
                if not isinstance(idx, int):
                    try:
                        idx = int(idx)
                    except Exception:
                        idx = 0
                current = tool_call_map.setdefault(idx, {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                })
                if item.get("id"):
                    current["id"] = item["id"]
                if item.get("type"):
                    current["type"] = item["type"]
                fn = item.get("function") or {}
                if isinstance(fn, dict):
                    if isinstance(fn.get("name"), str) and fn.get("name"):
                        current.setdefault("function", {}).update({"name": fn["name"]})
                    if isinstance(fn.get("arguments"), str) and fn.get("arguments"):
                        existing = str(current.setdefault("function", {}).get("arguments", ""))
                        current["function"]["arguments"] = existing + fn["arguments"]

    text = "".join(chunks)
    tool_calls = [tool_call_map[idx] for idx in sorted(tool_call_map.keys())]
    return {
        "choices": [{"message": {"content": text, "tool_calls": tool_calls}, "finish_reason": finish_reason}],
        "usage": {},
    }


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _responses_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/responses"
    return base + "/v1/responses"


def _extract_message_text_from_choice(choice: dict[str, Any]) -> str:
    if not isinstance(choice, dict):
        return ""

    message = choice.get("message") or {}
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content:
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text_part = item.get("text") or item.get("content")
                    if isinstance(text_part, str) and text_part:
                        parts.append(text_part)
            if parts:
                return "".join(parts)
        reasoning_content = message.get("reasoning_content")
        if isinstance(reasoning_content, str) and reasoning_content:
            return reasoning_content

    delta = choice.get("delta") or {}
    if isinstance(delta, dict):
        delta_content = delta.get("content")
        if isinstance(delta_content, str) and delta_content:
            return delta_content
        if isinstance(delta_content, list):
            parts: list[str] = []
            for item in delta_content:
                if isinstance(item, dict):
                    text_part = item.get("text") or item.get("content")
                    if isinstance(text_part, str) and text_part:
                        parts.append(text_part)
            if parts:
                return "".join(parts)
        reasoning_content = delta.get("reasoning_content")
        if isinstance(reasoning_content, str) and reasoning_content:
            return reasoning_content

    return ""


def _extract_tool_calls_from_choice(choice: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(choice, dict):
        return []
    message = choice.get("message") or {}
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            return [tc for tc in tool_calls if isinstance(tc, dict)]
    delta = choice.get("delta") or {}
    if isinstance(delta, dict):
        tool_calls = delta.get("tool_calls")
        if isinstance(tool_calls, list):
            return [tc for tc in tool_calls if isinstance(tc, dict)]
    return []


def _build_message_from_choice(choice: dict[str, Any]) -> dict[str, Any]:
    message = choice.get("message") if isinstance(choice, dict) else None
    if isinstance(message, dict):
        normalized = dict(message)
    else:
        normalized = {"role": "assistant"}
    normalized["content"] = _extract_message_text_from_choice(choice)
    tool_calls = _extract_tool_calls_from_choice(choice)
    if tool_calls:
        normalized["tool_calls"] = tool_calls
    # DeepSeek may put reasoning_content at choice level
    if isinstance(choice, dict):
        choice_rc = choice.get("reasoning_content")
        if choice_rc and isinstance(choice_rc, str) and choice_rc.strip():
            normalized["reasoning_content"] = choice_rc
    return normalized


def _build_usage_info(usage: dict[str, Any], *, model_name: str) -> dict[str, Any]:
    return {
        "model": model_name,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def _normalize_choice_payload(data: dict[str, Any], *, model_name: str) -> tuple[dict[str, Any], dict[str, Any], str, list[dict[str, Any]], str]:
    choices = data.get("choices") or []
    choice0 = choices[0] if choices else {}
    message = _build_message_from_choice(choice0)
    text = message.get("content", "") or ""
    tool_calls = message.get("tool_calls", []) if isinstance(message.get("tool_calls"), list) else []
    usage = _build_usage_info(data.get("usage") or {}, model_name=model_name)
    finish_reason = choice0.get("finish_reason", "") if isinstance(choice0, dict) else ""
    return choice0, message, text, tool_calls, finish_reason


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


def _tool_route_budget(message_count: int) -> tuple[int, float]:
    """Return (max_attempts, timeout_seconds_cap) for tool-chat routes.

    Keep short routes somewhat patient, but avoid turning upstream 504 streaks
    into multi-minute single-turn stalls. Deeper histories get progressively
    tighter budgets so degraded paths fail faster and surface fallback output.
    """
    if message_count >= 8:
        return 1, 600.0
    if message_count >= 6:
        return 2, 600.0
    if message_count >= 4:
        return 2, 600.0
    return 3, 600.0


def describe_tool_route_budget() -> list[dict[str, float | int]]:
    return [
        {"min_message_count": 0, "max_message_count": 3, "max_attempts": 3, "timeout_cap_seconds": 600.0},
        {"min_message_count": 4, "max_message_count": 5, "max_attempts": 2, "timeout_cap_seconds": 600.0},
        {"min_message_count": 6, "max_message_count": 7, "max_attempts": 2, "timeout_cap_seconds": 600.0},
        {"min_message_count": 8, "max_message_count": -1, "max_attempts": 1, "timeout_cap_seconds": 600.0},
    ]


class OpenAIResponsesClient:
    def __init__(self, config: ModelConfig, api_key: str) -> None:
        self._config = config
        self._api_key = api_key

    def request(self, input_payload, *, extra_payload: dict | None = None) -> dict:
        wire_api = (self._config.wire_api or "").strip().lower()
        if wire_api == "openai-completions":
            text, usage = self.chat(
                [{"role": "user", "content": str(input_payload)}],
                model=self._config.model,
                max_tokens=(extra_payload or {}).get("max_tokens", 500),
                temperature=(extra_payload or {}).get("temperature", 0.7),
                stream=False,
            )
            return {
                "object": "chat.completion",
                "model": self._config.model,
                "choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": usage,
            }

        url = _responses_url(self._config.base_url)
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
        url = _chat_completions_url(self._config.base_url)
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
                data = _safe_chat_completion_payload(response)
                _choice0, _message, text, _tool_calls, _finish_reason = _normalize_choice_payload(data, model_name=model_name)
                usage = _build_usage_info(data.get("usage") or {}, model_name=model_name)
                return text, usage
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

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ):
        """Stream tokens from chat completion, yielding content chunks one by one.

        Args:
            messages: List of message dicts with role/content.
            model: Model name override.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.

        Yields:
            str: Incremental content tokens as they arrive from the API.
        """
        model_name = model or self._config.model
        url = _chat_completions_url(self._config.base_url)
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
                        f"Chat stream request failed: {response.status_code} {body}",
                        status_code=response.status_code,
                        retryable=response.status_code >= 500,
                    )
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

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
        url = _chat_completions_url(self._config.base_url)
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
        tool_route_max_attempts, tool_route_timeout_cap = _tool_route_budget(len(messages))
        effective_timeout_seconds = min(self._config.timeout_seconds, tool_route_timeout_cap)
        with httpx.Client(timeout=_build_timeout(effective_timeout_seconds)) as client:
            tool_names = [tool.get("function", {}).get("name") for tool in tools]
            logger.info(
                "ModelClient.chat_with_tools model=%s tool_names=%s message_count=%s max_attempts=%s timeout_cap=%s",
                model_name,
                tool_names,
                len(messages),
                tool_route_max_attempts,
                effective_timeout_seconds,
            )
            last_error: Exception | None = None
            max_attempts = tool_route_max_attempts
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

                    # ── HTTP 响应有效，解析 & 空内容重试 ──
                    if response.status_code >= 400:
                        debug_path = Path('/tmp/agentsystem_chat_with_tools_payload.json')
                        try:
                            debug_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
                        except Exception:
                            pass
                        raise ModelClientError(
                            f"Chat with tools failed: {response.status_code} {response.text[:300]} | payload_dump={debug_path}",
                            status_code=response.status_code,
                            retryable=response.status_code >= 500 or response.status_code == 429,
                        )
                    data = _safe_chat_completion_payload(response)
                    choice, message, text, tool_calls, finish_reason = _normalize_choice_payload(data, model_name=model_name)
                    usage = _build_usage_info(data.get("usage") or {}, model_name=model_name)
                    logger.info(
                        "ModelClient.chat_with_tools response model=%s returned_tool_calls=%s finish_reason=%s attempt=%s/%s",
                        model_name,
                        [tc.get("function", {}).get("name") for tc in tool_calls],
                        finish_reason,
                        attempt + 1,
                        max_attempts,
                    )

                    # 模型返回空内容（无文字无工具调用）且还有重试次数时重试
                    if not text and not tool_calls and attempt < max_attempts - 1:
                        wait_seconds = 0.5 * (attempt + 1)
                        logger.warning(
                            "ModelClient.chat_with_tools empty_response model=%s attempt=%s/%s retry_in=%ss",
                            model_name,
                            attempt + 1,
                            max_attempts,
                            wait_seconds,
                        )
                        time.sleep(wait_seconds)
                        continue

                    return {
                        "message": message,
                        "text": text,
                        "tool_calls": tool_calls,
                        "finish_reason": finish_reason,
                    }, usage

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

        # 所有尝试耗尽仍未返回（不应发生）
        raise ModelClientError(
            "Chat with tools exhausted all attempts without returning a response",
            status_code=None,
            retryable=True,
        )

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
        max_turns: int = 30,
    ) -> tuple[str, dict]:
        """Multi-turn tool calling loop.
        Load max_turns from global config if not provided.

        1. Send system + user + tools -> LLM
        2. If tool_calls -> execute -> loop
        3. Until LLM gives final text answer
        """
        if max_turns is None:
            try:
                from app.services.turn_budget_policy import TurnBudgetPolicy, TaskModeBudget
                max_turns = TurnBudgetPolicy.decide(TaskModeBudget.EXECUTION)
            except Exception:
                max_turns = 30

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

        # 收敛提示阈值（turn≥CONVERGENCE_HINT_TURN 时注入）
        try:
            from app.services.turn_budget_policy import TurnBudgetPolicy
            _convergence_turn = TurnBudgetPolicy.CONVERGENCE_HINT_TURN
        except Exception:
            _convergence_turn = 50

        for turn in range(max_turns):
            # 到达收敛阈值时，注入阶段性收敛提示
            if turn == _convergence_turn:
                messages.append({
                    "role": "system",
                    "content": (
                        f"[系统提示] 当前对话已执行 {turn} 轮工具调用，接近预算上限。"
                        f"请立即整理已有信息，输出当前阶段性成果作为回复，不再调用工具。"
                    ),
                })

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
            # DeepSeek reasoning models include reasoning_content that must be
            # passed back on subsequent turns; preserve it if present and non-empty.
            reasoning = message.get("reasoning_content")
            if reasoning and isinstance(reasoning, str) and reasoning.strip():
                assistant_message["reasoning_content"] = reasoning
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
