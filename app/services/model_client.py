from __future__ import annotations

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
    ) -> str:
        """Send a chat completion request and return the assistant's text response.

        Uses streaming internally because the proxy strips content from
        non-streaming responses. Collects all delta content into a string.
        """
        model_name = model or self._config.model
        url = self._config.base_url.rstrip("/") + "/v1/chat/completions"
        payload: dict = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,  # always stream — proxy strips non-stream content
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
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            content_parts.append(delta["content"])
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue
        return "".join(content_parts)

    def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        *,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str:
        """Convenience: system + user message → assistant text."""
        return self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
