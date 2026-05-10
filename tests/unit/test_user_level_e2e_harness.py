from __future__ import annotations

from types import SimpleNamespace

import tests.e2e.test_50_scenarios_20_turns_user_level as harness


class _DummyResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


class _DummyClient:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        return _DummyResponse(200)

    def close(self) -> None:
        return None


def test_wait_for_service_disables_env_proxy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(*args, **kwargs):
        captured.update(kwargs)
        return _DummyClient(*args, **kwargs)

    monkeypatch.setattr(harness.httpx, "Client", fake_client)

    ok, detail = harness._wait_for_service("http://localhost:80", timeout_seconds=0.1)

    assert ok is True
    assert detail == "HTTP 200"
    assert captured["trust_env"] is False
    assert captured["timeout"] == 5.0


def test_e2e_client_disables_env_proxy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(*args, **kwargs):
        captured.update(kwargs)
        return _DummyClient(*args, **kwargs)

    monkeypatch.setattr(harness.httpx, "Client", fake_client)

    client = harness.E2EClient("http://localhost:80", timeout=42.0)

    assert client.base_url == "http://localhost:80"
    assert captured["timeout"] == 42.0
    assert captured["follow_redirects"] is False
    assert captured["trust_env"] is False
