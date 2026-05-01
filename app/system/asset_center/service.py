from __future__ import annotations

from app.system.asset_center.models import AssetDescriptorRecord, AssetModelRequirement
from app.system.asset_center.registry import AssetCenterRegistry
from app.system.model_runtime.model_client_registry import ModelRuntimeRecord


class AssetCenterService:
    def __init__(self, registry: AssetCenterRegistry | None = None) -> None:
        self._registry = registry or AssetCenterRegistry()

    @property
    def registry(self) -> AssetCenterRegistry:
        return self._registry

    def register_asset(self, descriptor: AssetDescriptorRecord) -> AssetDescriptorRecord:
        return self._registry.register_asset(descriptor)

    def register_model(self, record: ModelRuntimeRecord) -> ModelRuntimeRecord:
        return self._registry.register_model(record)

    def list_assets(self) -> list[dict[str, object]]:
        return [
            {
                "asset_id": descriptor.asset_id,
                "kind": descriptor.kind,
                "summary": descriptor.summary,
                "descriptor_version": descriptor.descriptor_version,
            }
            for descriptor in self._registry.list_assets()
        ]

    def list_models(self) -> list[dict[str, object]]:
        return [
            {
                "model_id": record.model_id,
                "provider": record.provider,
                "healthy": record.healthy,
                "role": record.role,
                "wire_api": record.wire_api,
            }
            for record in self._registry.list_models()
        ]

    def get_asset_detail(self, asset_id: str) -> dict[str, object]:
        descriptor = self._registry.require_asset(asset_id)
        return descriptor.to_dict()

    def get_asset_model_requirement(self, asset_id: str) -> AssetModelRequirement:
        return self._registry.get_asset_model_requirement(asset_id)
