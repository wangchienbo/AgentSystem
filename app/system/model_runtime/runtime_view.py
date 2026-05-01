from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.model_config import ModelConfig
from app.system.asset_center.service import AssetCenterService
from app.system.model_runtime.model_client_registry import ModelClientRegistry, ModelRuntimeRecord
from app.system.model_runtime.model_probe import ModelProbe


@dataclass(frozen=True)
class ModelRuntimeView:
    healthy: list[ModelRuntimeRecord]
    unhealthy: list[ModelRuntimeRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": [record.model_id for record in self.healthy],
            "unhealthy": [record.model_id for record in self.unhealthy],
        }


class ModelRuntimeRegistrar:
    def __init__(
        self,
        registry: ModelClientRegistry,
        probe: ModelProbe | None = None,
        asset_center: AssetCenterService | None = None,
    ) -> None:
        self._registry = registry
        self._probe = probe or ModelProbe()
        self._asset_center = asset_center
        self._records: dict[str, ModelRuntimeRecord] = {}

    def register_model(
        self,
        *,
        model_id: str,
        provider: str,
        config: ModelConfig,
        api_key: str,
        role: str = "secondary",
        metadata: dict[str, Any] | None = None,
        probe_client: Any | None = None,
    ) -> ModelRuntimeRecord:
        client = self._registry.register(model_id, config, api_key)
        record = ModelRuntimeRecord(
            model_id=model_id,
            provider=provider,
            base_url=config.base_url,
            api_key_env=config.api_key_env or "",
            wire_api=config.wire_api,
            enabled=True,
            healthy=False,
            role=role,
            metadata=metadata or {},
        )
        probed = self._probe.probe(record, probe_client or client)
        self._records[model_id] = probed
        if self._asset_center is not None:
            self._asset_center.register_model(probed)
        return probed

    def list_records(self) -> list[ModelRuntimeRecord]:
        return list(self._records.values())

    def runtime_view(self) -> ModelRuntimeView:
        healthy = [record for record in self._records.values() if record.healthy]
        unhealthy = [record for record in self._records.values() if not record.healthy]
        return ModelRuntimeView(healthy=healthy, unhealthy=unhealthy)
