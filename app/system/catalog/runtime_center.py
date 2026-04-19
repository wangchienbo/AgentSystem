from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.asset_contract import AssetCapability, AssetDescriptor, AssetKind, AssetState, AssetType, is_valid_asset_state_transition


class RuntimeCenter:
    """Runtime source of truth for live assets under the Phase H contract."""

    def __init__(self, data_file: str = "data/runtime_center.json") -> None:
        self._data_file = Path(data_file)
        self._lock = threading.RLock()
        self._entries: dict[str, AssetDescriptor] = {}
        self._load()

    def register_asset(self, descriptor: AssetDescriptor) -> AssetDescriptor:
        now = self._now_iso()
        if not descriptor.created_at:
            descriptor.created_at = now
        descriptor.updated_at = now
        if descriptor.status == AssetState.DECLARED:
            descriptor.status = AssetState.STARTING if descriptor.source_of_truth == "runtime" else AssetState.DECLARED
        self._entries[descriptor.asset_id] = descriptor
        self._save()
        return descriptor

    def register(
        self,
        asset_id: str,
        version: str,
        pid: int,
        endpoint: str,
        owner: str,
        status: str = "running",
        caller_id: str | None = None,
    ) -> AssetDescriptor:
        existing = self._entries.get(asset_id)
        if caller_id is not None and existing and existing.owner_id != caller_id and not caller_id.startswith("system"):
            raise PermissionError(f"caller {caller_id} cannot register asset {asset_id} owned by {existing.owner_id}")
        mapped_status = AssetState.ACTIVE if status == "running" else AssetState(status) if status in AssetState._value2member_map_ else AssetState.UNKNOWN
        metadata = {
            "pid": pid,
            "endpoint": endpoint,
            "legacy_runtime_status": status,
        }
        descriptor = AssetDescriptor(
            asset_id=asset_id,
            asset_type=AssetType.APP if asset_id.startswith("app.") else AssetType.SYSTEM,
            asset_kind=AssetKind.CORE_RUNTIME if owner == "system" else AssetKind.MATERIALIZED,
            version=version,
            owner_type="system" if owner == "system" else "user",
            owner_id=owner,
            source_of_truth="runtime",
            status=mapped_status,
            capabilities=[],
            invoke_contract={"type": "runtime_entry"},
            health_contract={"heartbeat": True},
            name=asset_id,
            description="runtime registered asset",
            metadata=metadata,
        )
        return self.register_asset(descriptor)

    def heartbeat(self, asset_id: str, pid: int | None = None) -> bool:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return False
            existing_pid = entry.metadata.get("pid")
            if pid is not None and existing_pid not in (None, pid):
                return False
            entry.updated_at = self._now_iso()
            entry.metadata["last_heartbeat"] = entry.updated_at
            if entry.status not in {AssetState.STOPPED, AssetState.REMOVED}:
                entry.status = AssetState.ACTIVE
            self._save()
            return True

    def update_status(self, asset_id: str, to_state: AssetState) -> bool:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return False
            if entry.status != to_state and not is_valid_asset_state_transition(entry.status, to_state):
                return False
            entry.status = to_state
            entry.updated_at = self._now_iso()
            self._save()
            return True

    def mark_crashed(self, asset_id: str) -> bool:
        return self.update_status(asset_id, AssetState.CRASHED)

    def mark_stopped(self, asset_id: str) -> bool:
        return self.update_status(asset_id, AssetState.STOPPED)

    def unregister(self, asset_id: str, pid: int | None = None) -> bool:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return False
            existing_pid = entry.metadata.get("pid")
            if pid is not None and existing_pid not in (None, pid):
                return False
            entry.status = AssetState.REMOVED
            entry.updated_at = self._now_iso()
            self._save()
            return True

    def get(self, asset_id: str) -> AssetDescriptor | None:
        with self._lock:
            entry = self._entries.get(asset_id)
            return AssetDescriptor.model_validate(entry.model_dump()) if entry else None

    def list_assets(self, asset_type: AssetType | None = None, status: AssetState | None = None) -> list[AssetDescriptor]:
        with self._lock:
            values = list(self._entries.values())
            if asset_type is not None:
                values = [v for v in values if v.asset_type == asset_type]
            if status is not None:
                values = [v for v in values if v.status == status]
            return [AssetDescriptor.model_validate(v.model_dump()) for v in values]

    def list_running(self) -> list[AssetDescriptor]:
        return self.list_assets(status=AssetState.ACTIVE)

    def list_all(self) -> list[AssetDescriptor]:
        return self.list_assets()

    def query_asset_info(self, asset_id: str) -> dict[str, Any] | None:
        asset = self.get(asset_id)
        if asset is None:
            return None
        return asset.model_dump(mode="json")

    def call_asset_method(self, asset_id: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        asset = self.get(asset_id)
        if asset is None:
            return {"ok": False, "error": f"asset {asset_id} not found"}
        allowed = {cap.method: cap for cap in asset.capabilities}
        if method not in allowed:
            return {"ok": False, "error": f"method {method} not exposed by {asset_id}"}
        return {
            "ok": True,
            "asset_id": asset_id,
            "method": method,
            "params": params or {},
            "state_change": None,
            "audit_ref": None,
            "note": "Phase H minimal contract only, execution mapping not wired yet",
        }

    def build_prompt(self, caller_id: str) -> str:
        entries = self.list_all()
        if caller_id != "system":
            entries = [e for e in entries if e.owner_id in {caller_id, caller_id.removeprefix("user."), "system"}]
        if not entries:
            return "当前没有运行中的实例。"
        return "\n".join(
            f"- {e.asset_id}: status={e.status.value}, owner={e.owner_id}, type={e.asset_type.value}" for e in entries
        )

    def _load(self) -> None:
        if not self._data_file.exists():
            return
        try:
            data = json.loads(self._data_file.read_text(encoding="utf-8"))
        except Exception:
            return
        entries = data.get("entries", {}) if isinstance(data, dict) else {}
        if not isinstance(entries, dict):
            return
        self._entries = {
            asset_id: AssetDescriptor.model_validate(entry)
            for asset_id, entry in entries.items()
            if isinstance(entry, dict)
        }

    def _save(self) -> None:
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": {asset_id: entry.model_dump(mode="json") for asset_id, entry in self._entries.items()}}
        self._data_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
