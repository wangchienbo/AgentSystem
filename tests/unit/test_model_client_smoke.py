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
