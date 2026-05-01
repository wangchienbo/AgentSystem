from __future__ import annotations

from dataclasses import replace

from app.system.asset_center.models import AssetDescriptorRecord
from app.system.model_runtime.model_client_registry import ModelRuntimeRecord


class AssetDescriptorValidationError(ValueError):
    pass


class AssetCenterRegistry:
    def __init__(self) -> None:
        self._descriptors: dict[str, AssetDescriptorRecord] = {}
        self._models: dict[str, ModelRuntimeRecord] = {}

    def register_asset(self, descriptor: AssetDescriptorRecord) -> AssetDescriptorRecord:
        self._validate_descriptor(descriptor)
        self._descriptors[descriptor.asset_id] = replace(descriptor)
        return self._descriptors[descriptor.asset_id]

    def register_model(self, record: ModelRuntimeRecord) -> ModelRuntimeRecord:
        self._models[record.model_id] = replace(record)
        return self._models[record.model_id]

    def list_assets(self) -> list[AssetDescriptorRecord]:
        return list(self._descriptors.values())

    def list_models(self) -> list[ModelRuntimeRecord]:
        return list(self._models.values())

    def get_asset_detail(self, asset_id: str) -> str:
        descriptor = self.require_asset(asset_id)
        return descriptor.detail

    def get_asset_model_requirement(self, asset_id: str):
        descriptor = self.require_asset(asset_id)
        return descriptor.model_requirement

    def require_asset(self, asset_id: str) -> AssetDescriptorRecord:
        try:
            return self._descriptors[asset_id]
        except KeyError as exc:
            raise KeyError(f"Asset descriptor not found: {asset_id}") from exc

    def _validate_descriptor(self, descriptor: AssetDescriptorRecord) -> None:
        if descriptor.descriptor_version < 1:
            raise AssetDescriptorValidationError("descriptor_version must be >= 1")
        if not descriptor.asset_id.strip():
            raise AssetDescriptorValidationError("asset_id is required")
        if not descriptor.kind.strip():
            raise AssetDescriptorValidationError("kind is required")
        if not descriptor.summary.strip():
            raise AssetDescriptorValidationError("summary is required")
        if not descriptor.detail.strip():
            raise AssetDescriptorValidationError("detail is required")
        method_names = [method.name for method in descriptor.methods]
        if len(method_names) != len(set(method_names)):
            raise AssetDescriptorValidationError("method names must be unique")
