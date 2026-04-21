from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.models.asset_contract import AssetDescriptor, AssetKind, AssetState, AssetType, is_valid_asset_state_transition
from app.models.context import SessionNode


class RuntimeCenter:
    """Runtime source of truth for live assets and session entities under Phase H."""

    def __init__(self, data_file: str = "data/runtime_center.json") -> None:
        self._data_file = Path(data_file)
        self._lock = threading.RLock()
        self._entries: dict[str, AssetDescriptor] = {}
        self._service_refs: dict[str, Any] = {}
        self._method_mappings: dict[tuple[str, str], Callable[..., Any]] = {}
        self._sessions: dict[str, SessionNode] = {}
        self._load()

    def register_asset(
        self,
        descriptor: AssetDescriptor,
        service_ref: Any | None = None,
        method_mappings: dict[str, Callable[..., Any]] | None = None,
    ) -> AssetDescriptor:
        now = self._now_iso()
        if not descriptor.created_at:
            descriptor.created_at = now
        descriptor.updated_at = now
        if descriptor.status == AssetState.DECLARED:
            descriptor.status = AssetState.STARTING if descriptor.source_of_truth == "runtime" else AssetState.DECLARED
        self._entries[descriptor.asset_id] = descriptor
        if service_ref is not None:
            self._service_refs[descriptor.asset_id] = service_ref
        if method_mappings:
            for method_name, handler in method_mappings.items():
                self._method_mappings[(descriptor.asset_id, method_name)] = handler
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
        metadata = {"pid": pid, "endpoint": endpoint, "legacy_runtime_status": status}
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

    def register_session(
        self,
        session_id: str,
        user_id: str,
        channel: str,
        kind: str = "root",
        parent_session_id: str | None = None,
        root_session_id: str | None = None,
        status: str = "active",
        actor: str = "interaction",
        topic_key: str = "",
    ) -> SessionNode:
        with self._lock:
            existing = self._sessions.get(session_id)
            now = datetime.now(timezone.utc)
            if existing is not None:
                existing.updated_at = now
                return existing
            node = SessionNode(
                session_id=session_id,
                user_id=user_id,
                channel=channel,
                kind=kind,
                actor=actor,
                topic_key=topic_key,
                parent_session_id=parent_session_id,
                root_session_id=root_session_id or (session_id if kind == "root" else parent_session_id),
                status=status,
                created_at=now,
                updated_at=now,
            )
            self._sessions[session_id] = node
            self._save()
            return node

    def get_session(self, session_id: str) -> SessionNode | None:
        with self._lock:
            node = self._sessions.get(session_id)
            return SessionNode.model_validate(node.model_dump()) if node else None

    def list_sessions(self, user_id: str | None = None) -> list[SessionNode]:
        with self._lock:
            values = list(self._sessions.values())
            if user_id is not None:
                values = [v for v in values if v.user_id == user_id]
            return [SessionNode.model_validate(v.model_dump()) for v in values]

    def touch_session(self, session_id: str) -> bool:
        with self._lock:
            node = self._sessions.get(session_id)
            if node is None:
                return False
            node.updated_at = datetime.now(timezone.utc)
            self._save()
            return True

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
            del self._entries[asset_id]
            self._save()
            return True

    def get_uptime(self, asset_id: str) -> str | None:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return None
            created_at = entry.created_at or entry.updated_at
            if not created_at:
                return None
            try:
                start = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                delta = now - start
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                if hours > 0:
                    return f"{hours}h {minutes}m"
                if minutes > 0:
                    return f"{minutes}m {seconds}s"
                return f"{seconds}s"
            except Exception:
                return None

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
            return self._call_error(asset_id, method, params, f"asset {asset_id} not found", error_type="asset_not_found")
        allowed = {cap.method: cap for cap in asset.capabilities}
        if method not in allowed:
            return self._call_error(asset_id, method, params, f"method {method} not exposed by {asset_id}", error_type="method_not_exposed")
        handler = self._method_mappings.get((asset_id, method))
        if handler is None:
            return self._call_error(asset_id, method, params, f"method mapping for {asset_id}.{method} is not wired yet", error_type="method_not_wired")
        try:
            result = handler(**(params or {})) if isinstance(params, dict) else handler(params)
        except TypeError:
            try:
                result = handler(params or {})
            except Exception as exc:
                return self._call_error(asset_id, method, params, str(exc), error_type=type(exc).__name__)
        except Exception as exc:
            return self._call_error(asset_id, method, params, str(exc), error_type=type(exc).__name__)
        return self._normalize_call_result(asset_id, method, params or {}, result)

    def _normalize_call_result(self, asset_id: str, method: str, params: dict[str, Any], result: Any) -> dict[str, Any]:
        base = {
            "asset_id": asset_id,
            "method": method,
            "params": params,
            "state_change": None,
            "audit_ref": None,
            "error": None,
            "error_type": None,
        }
        if isinstance(result, dict) and "success" in result and "data" in result:
            success = bool(result.get("success"))
            return {
                **base,
                "ok": success,
                "result": result.get("data"),
                "error": result.get("error") or (None if success else "asset method call failed"),
                "error_type": None if success else "tool_result_error",
                "raw_result": result,
            }
        if isinstance(result, dict) and result.get("status") == "error":
            return {
                **base,
                "ok": False,
                "result": None,
                "error": str(result.get("message") or "asset method call failed"),
                "error_type": "handler_error",
                "raw_result": result,
            }
        return {**base, "ok": True, "result": result, "raw_result": result}

    def _call_error(self, asset_id: str, method: str, params: dict[str, Any] | None, error: str, error_type: str) -> dict[str, Any]:
        return {
            "ok": False,
            "asset_id": asset_id,
            "method": method,
            "params": params or {},
            "result": None,
            "state_change": None,
            "audit_ref": None,
            "error": error,
            "error_type": error_type,
            "raw_result": None,
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

    def cleanup_expired(self, timeout_seconds: int = 300) -> list[str]:
        expired: list[str] = []
        now = datetime.now(timezone.utc)
        with self._lock:
            for asset_id, entry in self._entries.items():
                hb = entry.metadata.get("last_heartbeat") or entry.updated_at
                if not hb:
                    continue
                try:
                    seen = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
                except Exception:
                    continue
                if (now - seen).total_seconds() > timeout_seconds and entry.status == AssetState.ACTIVE:
                    entry.status = AssetState.CRASHED
                    entry.updated_at = self._now_iso()
                    expired.append(asset_id)
            if expired:
                self._save()
        return expired

    def _load(self) -> None:
        if not self._data_file.exists():
            return
        try:
            data = json.loads(self._data_file.read_text(encoding="utf-8"))
        except Exception:
            return
        entries = data.get("entries", {}) if isinstance(data, dict) else {}
        loaded: dict[str, AssetDescriptor] = {}
        if isinstance(entries, dict):
            for asset_id, entry in entries.items():
                if not isinstance(entry, dict):
                    continue
                try:
                    loaded[asset_id] = AssetDescriptor.model_validate(entry)
                except Exception:
                    legacy_type = entry.get("asset_type") or (AssetType.APP if "app" in asset_id else AssetType.SERVICE)
                    legacy_status = str(entry.get("status") or "unknown")
                    status_map = {
                        "running": AssetState.ACTIVE,
                        "created": AssetState.DECLARED,
                        "installed": AssetState.DECLARED,
                        "starting": AssetState.STARTING,
                        "stopped": AssetState.STOPPED,
                        "paused": AssetState.PAUSED,
                        "crashed": AssetState.CRASHED,
                        "degraded": AssetState.DEGRADED,
                        "unknown": AssetState.UNKNOWN,
                    }
                    loaded[asset_id] = AssetDescriptor(
                        asset_id=asset_id,
                        asset_type=legacy_type,
                        asset_kind=AssetKind.MATERIALIZED,
                        version=str(entry.get("version") or "1.0.0"),
                        owner_type=str(entry.get("owner_type") or "system"),
                        owner_id=str(entry.get("owner") or entry.get("owner_id") or "system"),
                        source_of_truth="runtime",
                        status=status_map.get(legacy_status, AssetState.UNKNOWN),
                        capabilities=[],
                        invoke_contract=entry.get("invoke_contract") or {},
                        health_contract=entry.get("health_contract") or {},
                        name=str(entry.get("name") or asset_id),
                        description=str(entry.get("description") or "legacy runtime entry"),
                        metadata={"legacy_entry": True, **(entry.get("metadata") or {})},
                        tags=list(entry.get("tags") or ["legacy-runtime"]),
                        created_at=str(entry.get("created_at") or entry.get("started_at") or self._now_iso()),
                        updated_at=str(entry.get("updated_at") or entry.get("last_heartbeat") or self._now_iso()),
                    )
        self._entries = loaded

        sessions = data.get("sessions", {}) if isinstance(data, dict) else {}
        loaded_sessions: dict[str, SessionNode] = {}
        if isinstance(sessions, dict):
            for session_id, node in sessions.items():
                if not isinstance(node, dict):
                    continue
                try:
                    loaded_sessions[session_id] = SessionNode.model_validate(node)
                except Exception:
                    continue
        self._sessions = loaded_sessions

    def _save(self) -> None:
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": {asset_id: entry.model_dump(mode="json") for asset_id, entry in self._entries.items()},
            "sessions": {session_id: node.model_dump(mode="json") for session_id, node in self._sessions.items()},
        }
        self._data_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
