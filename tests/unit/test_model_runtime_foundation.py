from __future__ import annotations

import pytest

from app.system.model_runtime.model_client_registry import ModelClientRegistry, ModelRuntimeRecord
from app.system.model_runtime.model_probe import ModelProbe
from app.system.model_runtime.model_selector import ModelSelectionError, ModelSelector
from app.models.model_config import ModelConfig
from app.ai.model_client import ModelClientError


class _HealthyProbeClient:
    def probe(self, prompt: str = "ping") -> dict:
        return {"ok": True, "prompt": prompt}


class _UnhealthyProbeClient:
    def probe(self, prompt: str = "ping") -> dict:
        raise ModelClientError("down")


def test_model_client_registry_registers_and_returns_client() -> None:
    registry = ModelClientRegistry()
    config = ModelConfig(base_url="https://example.invalid/v1", model="gpt-5.4")

    client = registry.register("gpt-5.4", config, api_key="sk-test")

    assert registry.get_client("gpt-5.4") is client
    assert registry.get_config("gpt-5.4").model == "gpt-5.4"
    assert registry.list_model_ids() == ["gpt-5.4"]


def test_model_probe_marks_record_healthy_on_success() -> None:
    probe = ModelProbe()
    record = ModelRuntimeRecord(
        model_id="gpt-5.4",
        provider="OpenAICompatible",
        base_url="https://example.invalid/v1",
        api_key_env="OPENAI_API_KEY",
        wire_api="openai-responses",
        enabled=True,
    )

    updated = probe.probe(record, _HealthyProbeClient())

    assert updated.healthy is True


def test_model_probe_marks_record_unhealthy_on_failure() -> None:
    probe = ModelProbe()
    record = ModelRuntimeRecord(
        model_id="gpt-5.4",
        provider="OpenAICompatible",
        base_url="https://example.invalid/v1",
        api_key_env="OPENAI_API_KEY",
        wire_api="openai-responses",
        enabled=True,
    )

    updated = probe.probe(record, _UnhealthyProbeClient())

    assert updated.healthy is False


def test_model_selector_prefers_healthy_preferred_model() -> None:
    selector = ModelSelector()
    records = [
        ModelRuntimeRecord(
            model_id="gpt-5.4",
            provider="OpenAICompatible",
            base_url="https://example.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            wire_api="openai-responses",
            enabled=True,
            healthy=True,
            metadata={"structured_output": True},
        ),
        ModelRuntimeRecord(
            model_id="gpt-4.1",
            provider="OpenAICompatible",
            base_url="https://example.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            wire_api="openai-responses",
            enabled=True,
            healthy=True,
            metadata={"structured_output": True},
        ),
    ]

    selected = selector.resolve(
        model_records=records,
        preferred_model="gpt-5.4",
        fallback_model="gpt-4.1",
        minimum_requirements={"structured_output": True},
    )

    assert selected.model_id == "gpt-5.4"
    assert selected.reason == "preferred"


def test_model_selector_falls_back_when_preferred_is_unhealthy() -> None:
    selector = ModelSelector()
    records = [
        ModelRuntimeRecord(
            model_id="gpt-5.4",
            provider="OpenAICompatible",
            base_url="https://example.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            wire_api="openai-responses",
            enabled=True,
            healthy=False,
            metadata={"structured_output": True},
        ),
        ModelRuntimeRecord(
            model_id="gpt-4.1",
            provider="OpenAICompatible",
            base_url="https://example.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            wire_api="openai-responses",
            enabled=True,
            healthy=True,
            metadata={"structured_output": True},
        ),
    ]

    selected = selector.resolve(
        model_records=records,
        preferred_model="gpt-5.4",
        fallback_model="gpt-4.1",
        minimum_requirements={"structured_output": True},
    )

    assert selected.model_id == "gpt-4.1"
    assert selected.reason == "fallback"


def test_model_selector_rejects_fallback_below_minimum_requirements() -> None:
    selector = ModelSelector()
    records = [
        ModelRuntimeRecord(
            model_id="gpt-5.4",
            provider="OpenAICompatible",
            base_url="https://example.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            wire_api="openai-responses",
            enabled=True,
            healthy=False,
            metadata={"structured_output": True},
        ),
        ModelRuntimeRecord(
            model_id="gpt-4.1",
            provider="OpenAICompatible",
            base_url="https://example.invalid/v1",
            api_key_env="OPENAI_API_KEY",
            wire_api="openai-responses",
            enabled=True,
            healthy=True,
            metadata={"structured_output": False},
        ),
    ]

    with pytest.raises(ModelSelectionError):
        selector.resolve(
            model_records=records,
            preferred_model="gpt-5.4",
            fallback_model="gpt-4.1",
            minimum_requirements={"structured_output": True},
        )
