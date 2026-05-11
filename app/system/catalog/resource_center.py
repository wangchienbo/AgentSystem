"""Resource Center — manages runtime instances, configurations, and state.

A Resource is a running instance with its current configuration and state.
This is the RUNTIME layer: separate from static asset definitions.

Key principle:
- Asset = static, installable definition (development-time)
- Resource = running instance + current config + current state (runtime)

The Resource Center reads its own core configuration from file at startup
(before any LLM calls), so it doesn't need to "derive how it works" at runtime.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime_paths import resolve_runtime_paths


@dataclass
class ResourceInstance:
    """A running resource instance."""
    resource_id: str              # e.g. "app.novel.instance.1"
    asset_id: str                 # which asset this is an instance of
    owner_id: str                 # "user.xxx" / "system"
    status: str = "running"       # "running" | "stopped" | "error"
    config: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    runtime_description: str = ""  # human-readable runtime context for LLM
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_llm_context(self) -> dict[str, Any]:
        """Return runtime context suitable for LLM consumption."""
        return {
            "resource_id": self.resource_id,
            "asset_id": self.asset_id,
            "status": self.status,
            "runtime_description": self.runtime_description,
            "config_summary": {k: v for k, v in self.config.items() if not k.startswith("_")},
        }


@dataclass
class ResourceCenterConfig:
    """Resource Center's own core configuration, file-fixed at startup.

    This is critical: the resource center must know how to find and manage
    resources BEFORE any LLM calls happen.
    """
    resource_store_path: str = "resources.json"
    max_instances_per_app: int = 10
    default_timeout_seconds: int = 300
    persistence_mode: str = "json"  # "json" | "sqlite"
    auto_cleanup_stopped: bool = True
    cleanup_after_hours: int = 24


class ResourceCenter:
    """Central manager for all runtime resource instances.

    Responsibilities:
    - Create/start/stop resource instances
    - Track per-instance configuration and state
    - Provide runtime context to LLM call chains
    - Persist resource state to disk
    - Enforce instance limits and lifecycle policies
    """

    def __init__(
        self,
        config: ResourceCenterConfig | None = None,
        data_dir: str | None = None,
    ) -> None:
        self._config = config or ResourceCenterConfig()
        self._data_dir = Path(data_dir) if data_dir else resolve_runtime_paths().data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._instances: dict[str, ResourceInstance] = {}
        self._load()

    # ---- Instance lifecycle ----

    def create_instance(
        self,
        resource_id: str,
        asset_id: str,
        owner_id: str,
        config: dict[str, Any] | None = None,
        runtime_description: str = "",
    ) -> ResourceInstance:
        """Create a new resource instance."""
        now = datetime.now(timezone.utc).isoformat()
        instance = ResourceInstance(
            resource_id=resource_id,
            asset_id=asset_id,
            owner_id=owner_id,
            config=config or {},
            runtime_description=runtime_description,
            created_at=now,
            updated_at=now,
        )
        self._instances[resource_id] = instance
        self._save()
        return instance

    def get_instance(self, resource_id: str) -> ResourceInstance | None:
        return self._instances.get(resource_id)

    def update_state(
        self,
        resource_id: str,
        state: dict[str, Any],
        config_update: dict[str, Any] | None = None,
    ) -> ResourceInstance | None:
        """Update instance state and optionally merge config."""
        instance = self._instances.get(resource_id)
        if not instance:
            return None
        instance.state.update(state)
        if config_update:
            instance.config.update(config_update)
        instance.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return instance

    def stop_instance(self, resource_id: str) -> bool:
        """Stop a resource instance."""
        instance = self._instances.get(resource_id)
        if not instance:
            return False
        instance.status = "stopped"
        instance.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def remove_instance(self, resource_id: str) -> bool:
        """Remove a resource instance entirely."""
        return self._instances.pop(resource_id, None) is not None

    # ---- Queries ----

    def list_instances(
        self,
        owner_id: str | None = None,
        asset_id: str | None = None,
        status: str | None = None,
    ) -> list[ResourceInstance]:
        """List resource instances with optional filters."""
        results = list(self._instances.values())
        if owner_id:
            results = [i for i in results if i.owner_id == owner_id]
        if asset_id:
            results = [i for i in results if i.asset_id == asset_id]
        if status:
            results = [i for i in results if i.status == status]
        return results

    def get_runtime_context_for_llm(
        self,
        owner_id: str | None = None,
        asset_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get runtime context suitable for LLM tool call chain."""
        instances = self.list_instances(owner_id=owner_id)
        if asset_ids:
            instances = [i for i in instances if i.asset_id in asset_ids]
        return [i.to_llm_context() for i in instances]

    # ---- Persistence ----

    def _load(self) -> None:
        path = self._data_dir / self._config.resource_store_path
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for rid, raw in data.get("instances", {}).items():
                    self._instances[rid] = ResourceInstance(**raw)
            except Exception:
                pass

    def _save(self) -> None:
        path = self._data_dir / self._config.resource_store_path
        data = {
            "instances": {
                rid: {
                    "resource_id": i.resource_id,
                    "asset_id": i.asset_id,
                    "owner_id": i.owner_id,
                    "status": i.status,
                    "config": i.config,
                    "state": i.state,
                    "created_at": i.created_at,
                    "updated_at": i.updated_at,
                    "runtime_description": i.runtime_description,
                    "metadata": i.metadata,
                }
                for rid, i in self._instances.items()
            }
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
