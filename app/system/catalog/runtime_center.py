from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class RuntimeEntry:
    asset_id: str
    version: str
    pid: int
    endpoint: str
    owner: str
    status: str = "running"
    started_at: str = ""
    last_heartbeat: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "RuntimeEntry":
        return cls(
            asset_id=str(data.get("asset_id", "")),
            version=str(data.get("version", "0.0.0")),
            pid=int(data.get("pid", 0) or 0),
            endpoint=str(data.get("endpoint", "")),
            owner=str(data.get("owner", "system")),
            status=str(data.get("status", "unknown")),
            started_at=str(data.get("started_at", "")),
            last_heartbeat=str(data.get("last_heartbeat", "")),
        )


class RuntimeCenter:
    """Dynamic runtime registry for running assets.

    Stores runtime-only process state in `data/runtime_center.json`.
    This is intentionally separate from AssetCenter, which manages static
    source/build/install lifecycle.
    """

    def __init__(self, data_file: str = "data/runtime_center.json") -> None:
        self._data_file = Path(data_file)
        self._lock = threading.RLock()
        self._entries: dict[str, RuntimeEntry] = {}
        self._load()

    def register(
        self,
        asset_id: str,
        version: str,
        pid: int,
        endpoint: str,
        owner: str,
        status: str = "running",
        caller_id: str | None = None,
    ) -> RuntimeEntry:
        """Register an asset in the runtime registry.

        N5-01: If caller_id is provided, enforce that a process can only
        register/update its own asset_id. Cross-asset writes are rejected.
        """
        now = self._now_iso()

        # Permission check: caller can only write their own asset_id
        if caller_id is not None:
            existing = self._entries.get(asset_id)
            if existing and existing.owner != caller_id and not caller_id.startswith("system."):
                raise PermissionError(
                    f"caller {caller_id} cannot register asset {asset_id} owned by {existing.owner}"
                )

        entry = RuntimeEntry(
            asset_id=asset_id,
            version=version,
            pid=pid,
            endpoint=endpoint,
            owner=owner,
            status=status,
            started_at=now,
            last_heartbeat=now,
        )
        with self._lock:
            self._entries[asset_id] = entry
            self._save()
        return entry

    def heartbeat(self, asset_id: str, pid: int | None = None) -> bool:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return False
            if pid is not None and entry.pid != pid:
                return False
            entry.last_heartbeat = self._now_iso()
            if entry.status != "stopped":
                entry.status = "running"
            self._save()
            return True

    def unregister(self, asset_id: str, pid: int | None = None) -> bool:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return False
            if pid is not None and entry.pid != pid:
                return False
            del self._entries[asset_id]
            self._save()
            return True

    def mark_crashed(self, asset_id: str) -> bool:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return False
            entry.status = "crashed"
            self._save()
            return True

    def mark_stopped(self, asset_id: str) -> bool:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return False
            entry.status = "stopped"
            self._save()
            return True

    def get(self, asset_id: str) -> RuntimeEntry | None:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry:
                return None
            return RuntimeEntry.from_dict(entry.to_dict())

    def list_running(self) -> list[RuntimeEntry]:
        with self._lock:
            return [
                RuntimeEntry.from_dict(entry.to_dict())
                for entry in self._entries.values()
                if entry.status == "running"
            ]

    def list_all(self) -> list[RuntimeEntry]:
        with self._lock:
            return [RuntimeEntry.from_dict(entry.to_dict()) for entry in self._entries.values()]

    def cleanup_expired(self, timeout_seconds: int = 90) -> list[str]:
        now = datetime.now(timezone.utc)
        expired: list[str] = []
        with self._lock:
            for asset_id, entry in self._entries.items():
                if not entry.last_heartbeat:
                    continue
                last = self._parse_iso(entry.last_heartbeat)
                if now - last > timedelta(seconds=timeout_seconds):
                    entry.status = "crashed"
                    expired.append(asset_id)
            if expired:
                self._save()
        return expired


    def build_prompt(self, caller_id: str) -> str:
        """Build a concise runtime summary for prompt injection."""
        entries = self.list_all()
        if caller_id != "system":
            entries = [
                entry for entry in entries
                if entry.owner == caller_id or entry.owner == caller_id.removeprefix("user.") or entry.owner == "system"
            ]
        if not entries:
            return "当前没有运行中的实例。"
        lines = []
        for entry in entries:
            lines.append(
                f"- {entry.asset_id}: status={entry.status}, owner={entry.owner}, endpoint={entry.endpoint or '-'}, pid={entry.pid}"
            )
        return "\n".join(lines)

    def get_uptime(self, asset_id: str) -> str | None:
        with self._lock:
            entry = self._entries.get(asset_id)
            if not entry or not entry.started_at:
                return None
            started = self._parse_iso(entry.started_at)
            delta = datetime.now(timezone.utc) - started
            seconds = int(delta.total_seconds())
            if seconds < 60:
                return f"{seconds}s"
            if seconds < 3600:
                return f"{seconds // 60}m"
            if seconds < 86400:
                return f"{seconds // 3600}h"
            return f"{seconds // 86400}d"

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
            asset_id: RuntimeEntry.from_dict(entry)
            for asset_id, entry in entries.items()
            if isinstance(entry, dict)
        }

    def _save(self) -> None:
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": {asset_id: entry.to_dict() for asset_id, entry in self._entries.items()},
        }
        self._data_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_iso(self, value: str) -> datetime:
        return datetime.fromisoformat(value)
