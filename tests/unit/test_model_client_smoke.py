from __future__ import annotations

import httpx
import pytest

from app.models.model_config import ModelConfig
from app.services.model_client import ModelClientError, OpenAIResponsesClient


class _FakeResponse:
    def __init__(self, status_code: int, content_type: str, body, text: str | None = None) -> None:
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._body = body
        self.text = text if text is not None else (body if isinstance(body, str) else str(body))

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _FakeStreamResponse(_FakeResponse):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.text.encode()

    def iter_lines(self):
        for line in self.text.splitlines():
            yield line


class _FakeClient:
    def __init__(self, response: _FakeResponse, captured: dict[str, object]) -> None:
        self._response = response
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, json: dict, headers: dict):
        self._captured["url"] = url
        self._captured["json"] = json
        self._captured["headers"] = headers
        return self._response

    def stream(self, method: str, url: str, json: dict, headers: dict):
        self._captured["method"] = method
        self._captured["url"] = url
        self._captured["json"] = json
        self._captured["headers"] = headers
        return self._response


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(base_url="https://example.test", model="gpt-5.4", timeout_seconds=12)


def test_probe_returns_json_payload_for_application_json(monkeypatch, model_config: ModelConfig) -> None:
    captured: dict[str, object] = {}
    response = _FakeResponse(
        status_code=200,
        content_type="application/json; charset=utf-8",
        body={"id": "resp_123", "output": [{"type": "message", "content": [{"type": "output_text", "text": "MODEL_PROBE_OK"}]}]},
    )

    def fake_client(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return _FakeClient(response, captured)

    monkeypatch.setattr(httpx, "Client", fake_client)
    client = OpenAIResponsesClient(config=model_config, api_key="sk-test")

    result = client.probe("Return only MODEL_PROBE_OK")

    assert captured["timeout"] == 12
    assert captured["url"] == "https://example.test/v1/responses"
    assert captured["json"] == {"model": "gpt-5.4", "input": "Return only MODEL_PROBE_OK"}
    assert captured["headers"] == {
        "Authorization": "Bearer sk-test",
        "Content-Type": "application/json",
    }
    assert result["id"] == "resp_123"


def test_request_supports_structured_input_payload(monkeypatch, model_config: ModelConfig) -> None:
    captured: dict[str, object] = {}
    response = _FakeResponse(
        status_code=200,
        content_type="application/json; charset=utf-8",
        body={"id": "resp_structured", "output_text": "ok"},
    )

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: _FakeClient(response, captured))
    client = OpenAIResponsesClient(config=model_config, api_key="sk-test")

    result = client.request(
        [{"role": "user", "content": [{"type": "input_text", "text": "hello"}]}],
        extra_payload={"metadata": {"source": "prompt-selection"}},
    )

    assert captured["json"] == {
        "model": "gpt-5.4",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "hello"}]}],
        "metadata": {"source": "prompt-selection"},
    }
    assert result["id"] == "resp_structured"


def test_probe_returns_stream_preview_for_sse_response(monkeypatch, model_config: ModelConfig) -> None:
    captured: dict[str, object] = {}
    stream_text = "event: response.output_text.delta\ndata: {\"delta\":\"MODEL_\"}\n\nevent: done\ndata: [DONE]\n"
    response = _FakeResponse(status_code=200, content_type="text/event-stream", body=stream_text, text=stream_text)

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: _FakeClient(response, captured))
    client = OpenAIResponsesClient(config=model_config, api_key="sk-test")

    result = client.probe("stream it")

    assert result["status_code"] == 200
    assert result["content_type"] == "text/event-stream"
    assert "MODEL_" in result["stream_preview"]


def test_probe_openai_completions_non_stream_falls_back_to_delta_content(monkeypatch) -> None:
    captured: dict[str, object] = {}
    model_config = ModelConfig(
        base_url="https://example.test/v1",
        model="deepseek-v4-pro",
        timeout_seconds=12,
        wire_api="openai-completions",
    )
    response = _FakeResponse(
        status_code=200,
        content_type="application/json; charset=utf-8",
        body={
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "MODEL_PROBE_OK"},
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": ""},
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        },
    )

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: _FakeClient(response, captured))
    client = OpenAIResponsesClient(config=model_config, api_key="sk-test")

    result = client.probe("Return only MODEL_PROBE_OK")

    assert result["choices"][0]["message"]["content"] == "MODEL_PROBE_OK"
    assert result["usage"]["total_tokens"] == 18


def test_probe_openai_completions_non_stream_falls_back_to_reasoning_content(monkeypatch) -> None:
    captured: dict[str, object] = {}
    model_config = ModelConfig(
        base_url="https://example.test/v1",
        model="qwen3.6-plus",
        timeout_seconds=12,
        wire_api="openai-completions",
    )
    response = _FakeResponse(
        status_code=200,
        content_type="application/json; charset=utf-8",
        body={
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "", "reasoning_content": "QWEN_REASONING_OK"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: _FakeClient(response, captured))
    client = OpenAIResponsesClient(config=model_config, api_key="sk-test")

    text, usage = client.chat([{"role": "user", "content": "ping"}], stream=False)

    assert text == "QWEN_REASONING_OK"
    assert usage["total_tokens"] == 15


def test_chat_with_tools_openai_completions_falls_back_to_delta_tool_calls(monkeypatch) -> None:
    captured: dict[str, object] = {}
    model_config = ModelConfig(
        base_url="https://example.test/v1",
        model="deepseek-v4-pro",
        timeout_seconds=12,
        wire_api="openai-completions",
    )
    response = _FakeResponse(
        status_code=200,
        content_type="application/json; charset=utf-8",
        body={
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": '{"path":"README.md"}'},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                    "message": {"role": "assistant", "content": ""},
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        },
    )

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: _FakeClient(response, captured))
    client = OpenAIResponsesClient(config=model_config, api_key="sk-test")

    result, usage = client.chat_with_tools(
        messages=[{"role": "user", "content": "read readme"}],
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )

    assert result["tool_calls"][0]["function"]["name"] == "read_file"
    assert result["finish_reason"] == "tool_calls"
    assert usage["total_tokens"] == 20


def test_chat_streaming_openai_completions_reads_delta_content(monkeypatch) -> None:
    captured: dict[str, object] = {}
    model_config = ModelConfig(
        base_url="https://example.test/v1",
        model="glm-5.1",
        timeout_seconds=12,
        wire_api="openai-completions",
    )
    stream_text = "\n".join([
        'data: {"choices":[{"delta":{"content":"MODEL_"}}]}',
        'data: {"choices":[{"delta":{"content":"PROBE_OK"}}],"usage":{"prompt_tokens":11,"completion_tokens":9}}',
        'data: [DONE]',
    ])
    response = _FakeStreamResponse(status_code=200, content_type="text/event-stream", body=stream_text, text=stream_text)

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: _FakeClient(response, captured))
    client = OpenAIResponsesClient(config=model_config, api_key="sk-test")

    text, usage = client.chat([{"role": "user", "content": "ping"}], stream=True)

    assert text == "MODEL_PROBE_OK"
    assert usage["prompt_tokens"] == 11
    assert usage["completion_tokens"] == 9


def test_probe_raises_retryable_error_for_server_failure(monkeypatch, model_config: ModelConfig) -> None:
    captured: dict[str, object] = {}
    response = _FakeResponse(
        status_code=503,
        content_type="application/json",
        body={"error": "upstream unavailable"},
        text='{"error":"upstream unavailable"}',
    )

    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: _FakeClient(response, captured))
    client = OpenAIResponsesClient(config=model_config, api_key="sk-test")

    with pytest.raises(ModelClientError) as exc_info:
        client.probe("ping")

    error = exc_info.value
    assert error.status_code == 503
    assert error.retryable is True
    assert "Model probe failed: 503" in str(error)
