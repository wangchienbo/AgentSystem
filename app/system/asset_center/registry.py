from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.system.asset_center.models import AssetDescriptorRecord, AssetSessionBindingRecord
from app.system.model_runtime.model_client_registry import ModelRuntimeRecord


class AssetDescriptorValidationError(ValueError):
    pass


class AssetCenterRegistry:
    def __init__(self) -> None:
        self._descriptors: dict[str, AssetDescriptorRecord] = {}
        self._models: dict[str, ModelRuntimeRecord] = {}
        self._session_bindings: dict[tuple[str, str], AssetSessionBindingRecord] = {}
        self._registration_epoch = 0

    def register_asset(self, descriptor: AssetDescriptorRecord) -> AssetDescriptorRecord:
        self._validate_descriptor(descriptor)
        self._registration_epoch += 1
        stored = replace(descriptor, registration_epoch=self._registration_epoch)
        self._descriptors[descriptor.asset_id] = stored
        return stored

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

    def upsert_session_binding(self, record: AssetSessionBindingRecord) -> AssetSessionBindingRecord:
        record.validate()
        now = datetime.now(timezone.utc).isoformat()
        key = (record.asset_id, record.upstream_session_id)
        existing = self._session_bindings.get(key)
        if existing is None:
            stored = replace(
                record,
                created_at=record.created_at or now,
                last_active_at=record.last_active_at or now,
            )
        else:
            if existing.local_session_id != record.local_session_id:
                raise ValueError(
                    "session binding uniqueness violated for "
                    f"{record.asset_id}:{record.upstream_session_id}"
                )
            stored = replace(
                existing,
                root_session_id=record.root_session_id or existing.root_session_id,
                parent_session_id=record.parent_session_id or existing.parent_session_id,
                status=record.status or existing.status,
                last_active_at=record.last_active_at or now,
                metadata=record.metadata or existing.metadata,
            )
        self._session_bindings[key] = stored
        return stored

    def get_session_binding(self, asset_id: str, upstream_session_id: str) -> AssetSessionBindingRecord | None:
        record = self._session_bindings.get((asset_id, upstream_session_id))
        return replace(record) if record is not None else None

    def list_session_bindings(self, asset_id: str | None = None) -> list[AssetSessionBindingRecord]:
        records = list(self._session_bindings.values())
        if asset_id is not None:
            records = [item for item in records if item.asset_id == asset_id]
        return [replace(item) for item in records]

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
