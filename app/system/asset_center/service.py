from __future__ import annotations

from app.system.asset_center.models import AssetDescriptorRecord, AssetModelRequirement
from app.system.asset_center.registry import AssetCenterRegistry


class AssetCenterService:
    def __init__(self, registry: AssetCenterRegistry | None = None) -> None:
        self._registry = registry or AssetCenterRegistry()

    @property
    def registry(self) -> AssetCenterRegistry:
        return self._registry

    def register_asset(self, descriptor: AssetDescriptorRecord) -> AssetDescriptorRecord:
        return self._registry.register_asset(descriptor)

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

    def get_asset_detail(self, asset_id: str) -> dict[str, object]:
        descriptor = self._registry.require_asset(asset_id)
        return descriptor.to_dict()

    def get_asset_model_requirement(self, asset_id: str) -> AssetModelRequirement:
        return self._registry.get_asset_model_requirement(asset_id)
