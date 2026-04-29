"""System Catalog — persistent registry of all assets (Apps, Skills, Paths).

Persistent registry of installed/static assets. The catalog is persisted to disk
so it survives restarts.

Storage:
  data/system_catalog.json  — system-level asset registry
  data/users/{user_id}.json  — per-user asset registry (already via UserService)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CatalogError(ValueError):
    pass


from app.system.runtime_asset_formatter import render_asset_overview_prompt


class CatalogEntry:
    """One asset entry in the system catalog."""

    def __init__(
        self,
        asset_id: str,
        asset_type: str,
        owner_id: str,
        name: str,
        description: str,
        status: str = "active",
        visibility: str = "public",
        interfaces: dict[str, Any] | None = None,
        required_role_level: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.asset_id = asset_id
        self.asset_type = asset_type  # "app", "skill", "path", "tool"
        self.owner_id = owner_id       # "system", "user.{id}", "app.{id}"
        self.name = name
        self.description = description
        self.status = status            # "active", "deprecated", "disabled"
        self.visibility = visibility    # "public", "private", "shared"
        self.interfaces = interfaces or {}  # {fn_key: {description, input_schema, output_schema}}
        self.required_role_level = required_role_level
        self.metadata = metadata or {}

    def overview_line(self) -> str:
        """Short overview for LLM prompt injection."""
        fn_names = ", ".join(self.interfaces.keys()) if self.interfaces else "无"
        return f"- {self.asset_id} ({self.name}): [{fn_names}] — {self.description}"

    def detail(self) -> dict[str, Any]:
        """Full detail for query_asset_detail tool."""
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "visibility": self.visibility,
            "owner_id": self.owner_id,
            "required_role_level": self.required_role_level,
            "interfaces": self.interfaces,
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "owner_id": self.owner_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "visibility": self.visibility,
            "interfaces": self.interfaces,
            "required_role_level": self.required_role_level,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CatalogEntry":
        return cls(
            asset_id=data["asset_id"],
            asset_type=data["asset_type"],
            owner_id=data["owner_id"],
            name=data["name"],
            description=data.get("description", ""),
            status=data.get("status", "active"),
            visibility=data.get("visibility", "public"),
            interfaces=data.get("interfaces"),
            required_role_level=data.get("required_role_level", 0),
            metadata=data.get("metadata"),
        )


class SystemCatalog:
    """Persistent static catalog for installed assets.

    System-level and user-level assets are stored together here as durable
    metadata, not as runtime heartbeat state.
    """

    def __init__(self, data_dir: str | None = None) -> None:
        base = data_dir or os.environ.get("AGENTSYSTEM_DATA_DIR", "data")
        self._data_dir = Path(base)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._catalog_path = self._data_dir / "system_catalog.json"

        self._lock = threading.RLock()
        self._entries: dict[str, CatalogEntry] = {}
        self._load()

    # -- Persistence --

    def _load(self) -> None:
        if self._catalog_path.exists():
            try:
                data = json.loads(self._catalog_path.read_text(encoding="utf-8"))
                for item in data if isinstance(data, list) else []:
                    entry = CatalogEntry.from_dict(item)
                    self._entries[entry.asset_id] = entry
                logger.info("Loaded %d catalog entries from %s", len(self._entries), self._catalog_path)
            except Exception as e:
                logger.warning("Failed to load catalog: %s", e)

    def _persist(self) -> None:
        try:
            data = [e.to_dict() for e in self._entries.values()]
            self._catalog_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            logger.error("Failed to persist catalog: %s", e)

    # -- Self-Registration --

    def register(self, entry: CatalogEntry) -> CatalogEntry:
        """Register (or update) an asset entry."""
        with self._lock:
            self._entries[entry.asset_id] = entry
            self._persist()
            logger.info("Catalog registered: %s (%s)", entry.asset_id, entry.name)
            return entry

    def unregister(self, asset_id: str) -> None:
        """Remove an asset entry."""
        with self._lock:
            if asset_id in self._entries:
                del self._entries[asset_id]
                self._persist()
                logger.info("Catalog unregistered: %s", asset_id)

    # -- Visibility Query --

    def get_visible_assets(self, caller_id: str) -> list[CatalogEntry]:
        """Return assets visible to the caller.

        Args:
            caller_id: "system", "user.{id}", or "app.{id}"
        """
        with self._lock:
            if caller_id == "system":
                return list(self._entries.values())
            elif caller_id.startswith("user."):
                return self._get_user_view(caller_id)
            elif caller_id.startswith("app."):
                return self._get_app_view(caller_id)
            else:
                return self._get_user_view(f"user.{caller_id}")

    def _get_user_view(self, user_id: str) -> list[CatalogEntry]:
        """User sees public assets + own assets."""
        result = []
        for entry in self._entries.values():
            if entry.visibility == "public":
                result.append(entry)
            elif entry.owner_id == user_id:
                result.append(entry)
        return result

    def _get_app_view(self, app_id: str) -> list[CatalogEntry]:
        """App sees public assets + its own assets."""
        result = []
        for entry in self._entries.values():
            if entry.visibility == "public":
                result.append(entry)
            elif entry.owner_id == app_id:
                result.append(entry)
        return result

    # -- Detail Lookup --

    def get_asset_detail(self, asset_id: str, caller_id: str) -> CatalogEntry | None:
        """Get full detail if visible to caller."""
        visible = self.get_visible_assets(caller_id)
        for entry in visible:
            if entry.asset_id == asset_id:
                return entry
        return None

    def get_entry(self, asset_id: str) -> CatalogEntry | None:
        """Direct lookup (no visibility check)."""
        return self._entries.get(asset_id)

    # -- Build asset overview prompt for LLM --

    def build_llm_prompt(self, caller_id: str) -> str:
        """Build a concise asset overview for LLM prompt injection."""
        assets = self.get_visible_assets(caller_id)
        return render_asset_overview_prompt(assets, header="## 可用资产概览")

    # -- Utility --

    def list_all(self) -> list[CatalogEntry]:
        return list(self._entries.values())

    def count(self) -> int:
        return len(self._entries)

    def update_status(self, asset_id: str, status: str) -> None:
        """Update an asset's status."""
        with self._lock:
            if asset_id in self._entries:
                self._entries[asset_id].status = status
                self._persist()
