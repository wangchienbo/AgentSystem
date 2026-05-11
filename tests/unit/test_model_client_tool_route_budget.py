from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.ai.model_client import OpenAIResponsesClient, ModelClientError
from app.models.model_config import ModelConfig


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json, headers):
        return self._response


def test_chat_with_tools_marks_429_as_retryable(tmp_path) -> None:
    client = OpenAIResponsesClient(
        ModelConfig(
            provider="openai_compatible",
            base_url="https://example.com/v1",
            model="test-model",
            timeout_seconds=5,
        ),
        api_key="test-key",
    )

    with patch("app.ai.model_client.httpx.Client", return_value=_FakeClient(_FakeResponse(429, '{"error":"rate limited"}'))):
        try:
            client.chat_with_tools(messages=[{"role": "user", "content": "ping"}], tools=[])
        except ModelClientError as exc:
            assert exc.status_code == 429
            assert exc.retryable is True
        else:
            raise AssertionError("expected ModelClientError")
