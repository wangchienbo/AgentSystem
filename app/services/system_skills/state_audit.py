from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.models.system_skill import SystemAuditRecord, SystemAuditRequest, SystemStateRequest, SystemStateResponse
from app.services.app_data_store import AppDataStore
from app.services.runtime_state_store import RuntimeStateStore


class SystemSkillError(ValueError):
    pass


class SystemStateService:
    def __init__(self, data_store: AppDataStore, store: RuntimeStateStore | None = None) -> None:
        self._data_store = data_store
        self._store = store
        self._state: dict[str, dict[str, Any]] = {}

    def ensure_initialized(self, app_instance_id: str) -> dict[str, Any]:
        self._data_store.get_namespace(f"{app_instance_id}:runtime_state")
        return self._state.setdefault(app_instance_id, {})

    def execute(self, app_instance_id: str, request: SystemStateRequest) -> SystemStateResponse:
        state = self.ensure_initialized(app_instance_id)
        if request.operation == "list":
            return SystemStateResponse(app_instance_id=app_instance_id, operation="list", values=deepcopy(state))
        if request.operation == "get":
            return SystemStateResponse(app_instance_id=app_instance_id, operation="get", key=request.key, value=deepcopy(state.get(request.key)), values=deepcopy(state))
        if request.operation == "set":
            if not request.key:
                raise SystemSkillError("State set requires key")
            state[request.key] = deepcopy(request.value)
            self._persist(app_instance_id)
            return SystemStateResponse(app_instance_id=app_instance_id, operation="set", key=request.key, value=deepcopy(request.value), values=deepcopy(state))
        if request.operation == "patch":
            if not request.key:
                raise SystemSkillError("State patch requires key")
            current = state.get(request.key, {})
            if not isinstance(current, dict) or not isinstance(request.value, dict):
                raise SystemSkillError("State patch requires dict target and dict value")
            patched = {**current, **request.value}
            state[request.key] = patched
            self._persist(app_instance_id)
            return SystemStateResponse(app_instance_id=app_instance_id, operation="patch", key=request.key, value=deepcopy(patched), values=deepcopy(state))
        if request.operation == "delete":
            if not request.key:
                raise SystemSkillError("State delete requires key")
            removed = state.pop(request.key, None)
            self._persist(app_instance_id)
            return SystemStateResponse(app_instance_id=app_instance_id, operation="delete", key=request.key, value=deepcopy(removed), values=deepcopy(state))
        raise SystemSkillError(f"Unsupported state operation: {request.operation}")

    def _persist(self, app_instance_id: str) -> None:
        self._data_store.put_record(namespace_id=f"{app_instance_id}:runtime_state", key="system_state", value={"values": self._state.get(app_instance_id, {})}, tags=["system", "state"])
        if self._store is not None:
            self._store._write_json("system_state_runtime", {key: value for key, value in self._state.items()})


class SystemAuditService:
    def __init__(self, data_store: AppDataStore, store: RuntimeStateStore | None = None) -> None:
        self._data_store = data_store
        self._store = store
        self._records: dict[str, list[SystemAuditRecord]] = {}

    def record(self, app_instance_id: str, request: SystemAuditRequest) -> SystemAuditRecord:
        self._data_store.get_namespace(f"{app_instance_id}:system_metadata")
        record = SystemAuditRecord(app_instance_id=app_instance_id, event_type=request.event_type, detail=deepcopy(request.detail), level=request.level)
        self._records.setdefault(app_instance_id, []).append(record)
        self._persist(app_instance_id)
        return record

    def list_records(self, app_instance_id: str) -> list[SystemAuditRecord]:
        return list(self._records.get(app_instance_id, []))

    def _persist(self, app_instance_id: str) -> None:
        self._data_store.put_record(namespace_id=f"{app_instance_id}:system_metadata", key="system_audit", value={"entries": [item.model_dump(mode="json") for item in self._records.get(app_instance_id, [])]}, tags=["system", "audit"])
        if self._store is not None:
            self._store.save_nested_mapping("system_audit_records", self._records)
