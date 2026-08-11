"""Regression tests for chat_with_tools retry paths.

Covers the two retry branches that were unified in model_client to use the
module-level helpers (_is_transient_status / _CHAT_TRANSPORT_ERRORS):

1. transient HTTP status (e.g. 502) is retried, then succeeds.
2. transport error (httpx.ReadTimeout) is retried, then succeeds.

These lock the behavior so future refactors of the retry logic can't silently
drop retry coverage.
"""

from __future__ import annotations

import httpx
import pytest

from app.ai.model_client import ModelClientError, OpenAIResponsesClient
from app.models.model_config import ModelConfig


class _FakeResponse:
    def __init__(self, status_code: int, content_type: str, body) -> None:
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._body = body

    @property
    def text(self) -> str:
        return self._body if isinstance(self._body, str) else str(self._body)

    def json(self):
        return self._body


class _SequenceFakeClient:
    """Returns responses in order; the final response is reused once exhausted."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.post_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json, headers):
        # 最后一项复用（模拟持续状态），否则按序列依次返回
        response = self._responses[min(self.post_count, len(self._responses) - 1)]
        self.post_count += 1
        return response


def _client() -> OpenAIResponsesClient:
    return OpenAIResponsesClient(
        ModelConfig(
            provider="openai_compatible",
            base_url="https://example.com/v1",
            model="test-model",
            timeout_seconds=5,
        ),
        api_key="test-key",
    )


def _success_response():
    return _FakeResponse(
        200,
        "application/json",
        {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        },
    )


def test_chat_with_tools_retries_transient_502_then_succeeds(monkeypatch) -> None:
    """统一到 _is_transient_status 后，502 仍应触发重试并最终成功。"""
    seq = _SequenceFakeClient(
        [_FakeResponse(502, "application/json", {"error": "bad gateway"}), _success_response()]
    )
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: seq)

    result, usage = _client().chat_with_tools(
        messages=[{"role": "user", "content": "ping"}], tools=[]
    )

    assert seq.post_count == 2, f"expected 2 posts (502 then success), got {seq.post_count}"
    assert result["text"] == "hello"
    assert result["finish_reason"] == "stop"
    assert usage["total_tokens"] == 8


def test_chat_with_tools_retries_transport_error_then_succeeds(monkeypatch) -> None:
    """统一到 _CHAT_TRANSPORT_ERRORS 后，ReadTimeout 仍应触发重试并最终成功。"""

    class _TransportFirstClient(_SequenceFakeClient):
        def post(self, url, json, headers):
            if self.post_count == 0:
                self.post_count += 1
                raise httpx.ReadTimeout("read timed out", request=None)
            return super().post(url, json, headers)

    seq = _TransportFirstClient([_success_response()])
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: seq)

    result, _usage = _client().chat_with_tools(
        messages=[{"role": "user", "content": "ping"}], tools=[]
    )

    assert seq.post_count == 2, f"expected 2 posts (transport error then success), got {seq.post_count}"
    assert result["text"] == "hello"


def test_chat_with_tools_transient_429_now_retried_then_succeeds(monkeypatch) -> None:
    """统一到 _is_transient_status 后，429（限流）也能走重试路径，而非立即抛错。"""
    seq = _SequenceFakeClient(
        [_FakeResponse(429, "application/json", {"error": "rate limited"}), _success_response()]
    )
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: seq)

    result, _usage = _client().chat_with_tools(
        messages=[{"role": "user", "content": "ping"}], tools=[]
    )

    assert seq.post_count == 2, f"expected 2 posts (429 then success), got {seq.post_count}"
    assert result["text"] == "hello"
