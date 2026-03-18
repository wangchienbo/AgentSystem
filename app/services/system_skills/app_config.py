from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.models.app_config import AppConfigMutation, AppConfigRequest, AppConfigResponse, AppConfigSnapshot
from app.services.app_data_store import AppDataStore
from app.services.runtime_state_store import RuntimeStateStore


class AppConfigError(ValueError):
    pass


class AppConfigService:
    def __init__(self, data_store: AppDataStore, store: RuntimeStateStore | None = None) -> None:
        self._data_store = data_store
        self._store = store
        self._snapshots: dict[str, AppConfigSnapshot] = {}
        self._history: dict[str, list[AppConfigMutation]] = {}

    def ensure_initialized(self, app_instance_id: str, defaults: dict[str, Any] | None = None, schema: dict[str, Any] | None = None) -> AppConfigSnapshot:
        if app_instance_id in self._snapshots:
            return self._snapshots[app_instance_id]
        self._data_store.get_namespace(f"{app_instance_id}:system_metadata")
        snapshot = AppConfigSnapshot(
            app_instance_id=app_instance_id,
            values=deepcopy(defaults or {}),
            config_schema=deepcopy(schema or {}),
        )
        self._snapshots[app_instance_id] = snapshot
        self._history.setdefault(app_instance_id, []).append(
            AppConfigMutation(app_instance_id=app_instance_id, action="init", value=deepcopy(snapshot.values))
        )
        self._persist_snapshot(app_instance_id)
        return snapshot

    def get_snapshot(self, app_instance_id: str) -> AppConfigSnapshot:
        if app_instance_id not in self._snapshots:
            raise AppConfigError(f"App config not initialized: {app_instance_id}")
        return self._snapshots[app_instance_id]

    def list_values(self, app_instance_id: str) -> AppConfigResponse:
        snapshot = self.get_snapshot(app_instance_id)
        return AppConfigResponse(
            app_instance_id=app_instance_id,
            operation="list",
            values=deepcopy(snapshot.values),
            history_count=len(self._history.get(app_instance_id, [])),
        )

    def execute(self, app_instance_id: str, request: AppConfigRequest) -> AppConfigResponse:
        if app_instance_id not in self._snapshots:
            self.ensure_initialized(app_instance_id, schema=request.config_schema)
        snapshot = self._snapshots[app_instance_id]

        if request.operation == "list":
            return self.list_values(app_instance_id)
        if request.operation == "get":
            value = snapshot.values.get(request.key)
            return AppConfigResponse(app_instance_id=app_instance_id, operation="get", key=request.key, value=deepcopy(value), values=deepcopy(snapshot.values), history_count=len(self._history.get(app_instance_id, [])))
        if request.operation == "set":
            if not request.key:
                raise AppConfigError("Config set requires key")
            snapshot.values[request.key] = deepcopy(request.value)
            self._history.setdefault(app_instance_id, []).append(AppConfigMutation(app_instance_id=app_instance_id, action="set", key=request.key, value=deepcopy(request.value)))
            self._persist_snapshot(app_instance_id)
            return AppConfigResponse(app_instance_id=app_instance_id, operation="set", key=request.key, value=deepcopy(request.value), values=deepcopy(snapshot.values), history_count=len(self._history.get(app_instance_id, [])))
        if request.operation == "patch":
            if not request.key:
                raise AppConfigError("Config patch requires key")
            current = snapshot.values.get(request.key, {})
            if not isinstance(current, dict) or not isinstance(request.value, dict):
                raise AppConfigError("Config patch requires dict target and dict value")
            patched = {**current, **request.value}
            snapshot.values[request.key] = patched
            self._history.setdefault(app_instance_id, []).append(AppConfigMutation(app_instance_id=app_instance_id, action="patch", key=request.key, value=deepcopy(request.value)))
            self._persist_snapshot(app_instance_id)
            return AppConfigResponse(app_instance_id=app_instance_id, operation="patch", key=request.key, value=deepcopy(patched), values=deepcopy(snapshot.values), history_count=len(self._history.get(app_instance_id, [])))
        if request.operation == "delete":
            if not request.key:
                raise AppConfigError("Config delete requires key")
            removed = snapshot.values.pop(request.key, None)
            self._history.setdefault(app_instance_id, []).append(AppConfigMutation(app_instance_id=app_instance_id, action="delete", key=request.key, value=deepcopy(removed)))
            self._persist_snapshot(app_instance_id)
            return AppConfigResponse(app_instance_id=app_instance_id, operation="delete", key=request.key, value=deepcopy(removed), values=deepcopy(snapshot.values), history_count=len(self._history.get(app_instance_id, [])))
        raise AppConfigError(f"Unsupported config operation: {request.operation}")

    def list_history(self, app_instance_id: str) -> list[AppConfigMutation]:
        return list(self._history.get(app_instance_id, []))

    def _persist_snapshot(self, app_instance_id: str) -> None:
        snapshot = self._snapshots[app_instance_id]
        self._data_store.put_record(namespace_id=f"{app_instance_id}:system_metadata", key="app_config", value={"values": snapshot.values, "config_schema": snapshot.config_schema, "updated_at": snapshot.updated_at.isoformat()}, tags=["system", "config"])
        self._data_store.put_record(namespace_id=f"{app_instance_id}:system_metadata", key="app_config_history", value={"entries": [item.model_dump(mode="json") for item in self._history.get(app_instance_id, [])]}, tags=["system", "config", "history"])
        if self._store is not None:
            self._store.save_mapping("app_config_snapshots", self._snapshots)
            self._store.save_nested_mapping("app_config_history", self._history)
