from __future__ import annotations

from app.ai.model_client import ModelClientError
from app.models.model_config import ModelConfig
from app.system.asset_center.service import AssetCenterService
from app.system.asset_center.models import InteractionDecisionEnvelope
from app.system.model_runtime.model_client_registry import ModelClientRegistry
from app.system.model_runtime.runtime_view import ModelRuntimeRegistrar


class _HealthyProbeClient:
    def probe(self, prompt: str = "ping") -> dict:
        return {"ok": True}


class _UnhealthyProbeClient:
    def probe(self, prompt: str = "ping") -> dict:
        raise ModelClientError("down")


def test_asset_center_can_list_registered_models() -> None:
    asset_center = AssetCenterService()
    registry = ModelClientRegistry()
    registrar = ModelRuntimeRegistrar(registry=registry, asset_center=asset_center)

    config = ModelConfig(base_url="https://example.invalid/v1", model="gpt-5.4", api_key_env="OPENAI_API_KEY", wire_api="responses")
    registrar.register_model(
        model_id="gpt-5.4",
        provider="OpenAICompatible",
        config=config,
        api_key="sk-test",
        role="primary",
        probe_client=_HealthyProbeClient(),
    )

    models = asset_center.list_models()
    assert models == [
        {
            "model_id": "gpt-5.4",
            "provider": "OpenAICompatible",
            "healthy": True,
            "role": "primary",
            "wire_api": "responses",
        }
    ]


def test_model_runtime_view_separates_healthy_and_unhealthy_records() -> None:
    registry = ModelClientRegistry()
    registrar = ModelRuntimeRegistrar(registry=registry)

    healthy_config = ModelConfig(base_url="https://example.invalid/v1", model="gpt-5.4", api_key_env="OPENAI_API_KEY", wire_api="responses")
    unhealthy_config = ModelConfig(base_url="https://example.invalid/v1", model="gpt-4.1", api_key_env="OPENAI_API_KEY", wire_api="responses")

    registrar.register_model(
        model_id="gpt-5.4",
        provider="OpenAICompatible",
        config=healthy_config,
        api_key="sk-test",
        probe_client=_HealthyProbeClient(),
    )
    registrar.register_model(
        model_id="gpt-4.1",
        provider="OpenAICompatible",
        config=unhealthy_config,
        api_key="sk-test",
        probe_client=_UnhealthyProbeClient(),
    )

    view = registrar.runtime_view()
    assert [record.model_id for record in view.healthy] == ["gpt-5.4"]
    assert [record.model_id for record in view.unhealthy] == ["gpt-4.1"]


def test_interaction_decision_envelope_v1_validation() -> None:
    InteractionDecisionEnvelope(decision="text", text="ok").validate()
    InteractionDecisionEnvelope(decision="need_asset_detail_id", need_asset_detail_id="asset:self-iteration:v1").validate()
    InteractionDecisionEnvelope(decision="invoke", invoke={"asset_id": "asset:self-iteration:v1", "method": "run", "params": {}}).validate()
