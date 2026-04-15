"""Persistence Service — app state persistence & recovery.

Serializes the entire runtime state (app instances, lifecycle events,
leases, checkpoints, pending tasks, registry entries, catalog entries,
and session data) to JSON on disk so the system survives restarts.

Graceful degradation: corrupted files are quarantined and the system
starts fresh rather than crashing.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _quarantine(path: Path) -> None:
    """Move a corrupted file to a quarantine directory."""
    try:
        qdir = path.parent / "corrupted"
        qdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        target = qdir / f"{path.stem}.{ts}.bak"
        shutil.move(str(path), str(target))
        logger.warning("Corrupted persistence file quarantined: %s → %s", path, target)
    except OSError as e:
        logger.error("Failed to quarantine %s: %s", path, e)


# ---------------------------------------------------------------------------
# Persistence Service
# ---------------------------------------------------------------------------

class PersistenceError(Exception):
    pass


class PersistenceService:
    """Central persistence service for AgentSystem runtime state.

    Saves and restores:
    - App instances (from lifecycle service)
    - Lifecycle events
    - Runtime leases & checkpoints (from runtime host)
    - Pending tasks
    - Registry entries & blueprints
    - Catalog entries
    - LightBrain session metadata (sessions themselves persist via
      LightBrainMemory's own JSON files; we just save a cross-reference
      index here for fast restore).

    Usage:
        svc = PersistenceService(data_dir="data/persistence")
        svc.restore_state(lifecycle, runtime_host, registry, catalog)
        # ... system runs ...
        svc.save_state(lifecycle, runtime_host, registry, catalog)
    """

    STATE_FILE = "agent_state.json"

    def __init__(self, data_dir: str | None = None) -> None:
        base = data_dir or os.environ.get("AGENTSYSTEM_PERSISTENCE_DIR", "data/persistence")
        self._data_dir = Path(base)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._data_dir / self.STATE_FILE
        self._last_save: datetime | None = None

    # -- public API ----------------------------------------------------------

    @property
    def state_file(self) -> Path:
        return self._state_file

    def save_state(
        self,
        lifecycle: Any = None,
        runtime_host: Any = None,
        registry: Any = None,
        catalog: Any = None,
        light_brain_memory: Any = None,
    ) -> Path:
        """Serialize current runtime state to disk.

        Args:
            lifecycle: AppLifecycleService (optional)
            runtime_host: AppRuntimeHostService (optional)
            registry: AppRegistryService (optional)
            catalog: AppCatalogService (optional)
            light_brain_memory: LightBrainMemory (optional)

        Returns:
            Path to the written state file.
        """
        state: dict[str, Any] = {
            "version": 1,
            "saved_at": _iso(datetime.now(UTC)),
            "app_instances": self._serialize_app_instances(lifecycle),
            "lifecycle_events": self._serialize_lifecycle_events(lifecycle),
            "runtime_leases": self._serialize_runtime_leases(runtime_host),
            "runtime_checkpoints": self._serialize_runtime_checkpoints(runtime_host),
            "runtime_pending_tasks": self._serialize_pending_tasks(runtime_host),
            "registry_entries": self._serialize_registry_entries(registry),
            "catalog_entries": self._serialize_catalog_entries(catalog),
            "session_index": self._serialize_session_index(light_brain_memory),
        }

        try:
            # Atomic write: write to temp then rename
            tmp = self._state_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(state, indent=2, ensure_ascii=False, default=_json_default),
                encoding="utf-8",
            )
            tmp.replace(self._state_file)
            self._last_save = datetime.now(UTC)
            logger.info("State saved to %s", self._state_file)
            return self._state_file
        except OSError as e:
            raise PersistenceError(f"Failed to save state: {e}")

    def restore_state(
        self,
        lifecycle: Any = None,
        runtime_host: Any = None,
        registry: Any = None,
        catalog: Any = None,
        light_brain_memory: Any = None,
    ) -> dict[str, int]:
        """Load state from disk and re-register apps, restore sessions.

        Returns a summary dict with counts of restored items.
        """
        if not self._state_file.exists():
            logger.info("No persistence file found at %s, starting fresh", self._state_file)
            return {"status": "no_state_file"}

        try:
            raw = self._state_file.read_text(encoding="utf-8")
            if not raw.strip():
                _quarantine(self._state_file)
                return {"status": "quarantined_empty"}
            state = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Corrupted persistence file, quarantining: %s", e)
            _quarantine(self._state_file)
            return {"status": "quarantined_corrupted", "error": str(e)}

        # Validate version
        version = state.get("version", 0)
        if version != 1:
            logger.warning("Unknown persistence version %d, attempting best-effort restore", version)

        restored: dict[str, int] = {"status": "restored"}

        # Restore app instances and lifecycle events
        if lifecycle is not None:
            restored["app_instances"] = self._restore_app_instances(state.get("app_instances", []), lifecycle)
            restored["lifecycle_events"] = self._restore_lifecycle_events(state.get("lifecycle_events", {}), lifecycle)

        # Restore runtime host state
        if runtime_host is not None:
            restored["runtime_leases"] = self._restore_runtime_leases(
                state.get("runtime_leases", []), runtime_host
            )
            restored["runtime_checkpoints"] = self._restore_runtime_checkpoints(
                state.get("runtime_checkpoints", {}), runtime_host
            )
            restored["pending_tasks"] = self._restore_pending_tasks(
                state.get("runtime_pending_tasks", {}), runtime_host
            )

        # Restore registry
        if registry is not None:
            restored["registry_entries"] = self._restore_registry_entries(
                state.get("registry_entries", {}), registry
            )

        # Restore catalog
        if catalog is not None:
            restored["catalog_entries"] = self._restore_catalog_entries(
                state.get("catalog_entries", []), catalog
            )

        logger.info("State restored from %s: %s", self._state_file, restored)
        return restored

    # -- serializers ---------------------------------------------------------

    def _serialize_app_instances(self, lifecycle: Any) -> list[dict[str, Any]]:
        if lifecycle is None or not hasattr(lifecycle, "_instances"):
            return []
        items = []
        for inst in lifecycle._instances.values():
            items.append({
                "id": inst.id,
                "blueprint_id": inst.blueprint_id,
                "owner_user_id": inst.owner_user_id,
                "status": inst.status,
                "installed_version": inst.installed_version,
                "data_namespace": inst.data_namespace,
                "execution_mode": inst.execution_mode,
                "runtime_policy": inst.runtime_policy.model_dump(mode="json") if hasattr(inst.runtime_policy, "model_dump") else {},
                "system_skills": list(inst.system_skills),
                "resolved_skills": list(inst.resolved_skills),
                "runtime_profile": inst.runtime_profile.model_dump(mode="json") if hasattr(inst.runtime_profile, "model_dump") else {},
                "skill_instances": dict(inst.skill_instances) if inst.skill_instances else {},
            })
        return items

    def _serialize_lifecycle_events(self, lifecycle: Any) -> dict[str, list[dict[str, Any]]]:
        if lifecycle is None or not hasattr(lifecycle, "_events"):
            return {}
        result = {}
        for app_id, events in lifecycle._events.items():
            result[app_id] = [
                {
                    "app_instance_id": e.app_instance_id,
                    "event_type": e.event_type,
                    "from_status": e.from_status,
                    "to_status": e.to_status,
                    "reason": e.reason,
                    "created_at": _iso(e.created_at),
                }
                for e in events
            ]
        return result

    def _serialize_runtime_leases(self, runtime_host: Any) -> list[dict[str, Any]]:
        if runtime_host is None or not hasattr(runtime_host, "_leases"):
            return []
        return [
            {
                "app_instance_id": lease.app_instance_id,
                "status": lease.status,
                "health": lease.health,
                "last_heartbeat_at": _iso(lease.last_heartbeat_at),
                "restart_count": lease.restart_count,
            }
            for lease in runtime_host._leases.values()
        ]

    def _serialize_runtime_checkpoints(self, runtime_host: Any) -> dict[str, list[dict[str, Any]]]:
        if runtime_host is None or not hasattr(runtime_host, "_checkpoints"):
            return {}
        result = {}
        for app_id, cps in runtime_host._checkpoints.items():
            result[app_id] = [
                {
                    "checkpoint_id": cp.checkpoint_id,
                    "app_instance_id": cp.app_instance_id,
                    "status": cp.status,
                    "pending_tasks": list(cp.pending_tasks),
                    "metadata": dict(cp.metadata),
                    "created_at": _iso(cp.created_at),
                }
                for cp in cps
            ]
        return result

    def _serialize_pending_tasks(self, runtime_host: Any) -> dict[str, list[str]]:
        if runtime_host is None or not hasattr(runtime_host, "_pending_tasks"):
            return {}
        return dict(runtime_host._pending_tasks)

    def _serialize_registry_entries(self, registry: Any) -> dict[str, Any]:
        if registry is None:
            return {"blueprints": {}, "entries": {}}
        blueprints = {}
        if hasattr(registry, "_blueprints"):
            for bp_id, bp in registry._blueprints.items():
                blueprints[bp_id] = {
                    "id": bp.id,
                    "name": bp.name,
                    "version": bp.version,
                    "goal": bp.goal,
                    "app_shape": bp.app_shape,
                    "required_skills": list(bp.required_skills),
                    "runtime_policy": bp.runtime_policy.model_dump(mode="json") if hasattr(bp.runtime_policy, "model_dump") else {},
                    "runtime_profile": bp.runtime_profile.model_dump(mode="json") if hasattr(bp.runtime_profile, "model_dump") else {},
                }
        entries = {}
        if hasattr(registry, "_entries"):
            for eid, entry in registry._entries.items():
                entries[eid] = {
                    "blueprint_id": entry.blueprint_id,
                    "name": entry.name,
                    "version": entry.version,
                    "description": entry.description,
                    "release_status": entry.release_status,
                    "approved_at": _iso(entry.approved_at),
                    "app_shape": entry.app_shape,
                    "releases": [
                        {
                            "version": r.version,
                            "status": r.status,
                            "note": r.note,
                            "reviewer": r.reviewer,
                            "app_shape": r.app_shape,
                            "required_skills": list(r.required_skills),
                            "runtime_policy": r.runtime_policy,
                            "runtime_profile": r.runtime_profile,
                            "created_at": _iso(r.created_at),
                            "approved_at": _iso(r.approved_at),
                        }
                        for r in entry.releases
                    ],
                }
        return {"blueprints": blueprints, "entries": entries}

    def _serialize_catalog_entries(self, catalog: Any) -> list[dict[str, Any]]:
        if catalog is None or not hasattr(catalog, "_apps"):
            return []
        return [
            {
                "app_id": entry.app_id,
                "name": entry.name,
                "description": entry.description,
                "execution_mode": entry.execution_mode,
                "trigger_phrases": list(entry.trigger_phrases),
                "blueprint_id": entry.blueprint_id,
                "version": entry.version,
            }
            for entry in catalog._apps.values()
        ]

    def _serialize_session_index(self, memory: Any) -> list[dict[str, Any]]:
        """Save a lightweight session index (session files persist on their own)."""
        if memory is None or not hasattr(memory, "_sessions"):
            return []
        return [
            {
                "session_id": s.session_id,
                "user_id": s.user_id,
                "channel": s.channel,
                "created_at": _iso(s.created_at),
                "last_active_at": _iso(s.last_active_at),
                "message_count": len(s.messages),
                "related_apps": sorted(s.related_apps),
            }
            for s in memory._sessions.values()
        ]

    # -- deserializers / restorers -------------------------------------------

    def _restore_app_instances(self, instances: list[dict], lifecycle: Any) -> int:
        from app.models.app_instance import AppInstance
        from app.models.runtime_policy import RuntimePolicy
        from app.models.app_profile import AppRuntimeProfile

        count = 0
        for data in instances:
            try:
                runtime_policy = RuntimePolicy(**data.get("runtime_policy", {}))
                runtime_profile = AppRuntimeProfile(**data.get("runtime_profile", {}))
                instance = AppInstance(
                    id=data["id"],
                    blueprint_id=data["blueprint_id"],
                    owner_user_id=data["owner_user_id"],
                    status=data["status"],
                    installed_version=data.get("installed_version", "0.1.0"),
                    data_namespace=data.get("data_namespace", ""),
                    execution_mode=data.get("execution_mode", "service"),
                    runtime_policy=runtime_policy,
                    system_skills=data.get("system_skills", []),
                    resolved_skills=data.get("resolved_skills", []),
                    runtime_profile=runtime_profile,
                    skill_instances=data.get("skill_instances", {}),
                )
                lifecycle.register_instance(instance)
                count += 1
            except Exception as e:
                logger.warning("Failed to restore app instance %s: %s", data.get("id", "?"), e)
        return count

    def _restore_lifecycle_events(self, events: dict[str, list[dict]], lifecycle: Any) -> int:
        from app.models.runtime import LifecycleEvent

        count = 0
        for app_id, event_list in events.items():
            lifecycle._events.setdefault(app_id, [])
            for data in event_list:
                try:
                    evt = LifecycleEvent(
                        app_instance_id=data["app_instance_id"],
                        event_type=data["event_type"],
                        from_status=data["from_status"],
                        to_status=data["to_status"],
                        reason=data.get("reason", ""),
                        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC),
                    )
                    lifecycle._events[app_id].append(evt)
                    count += 1
                except Exception as e:
                    logger.warning("Failed to restore lifecycle event for %s: %s", app_id, e)
        return count

    def _restore_runtime_leases(self, leases: list[dict], runtime_host: Any) -> int:
        from app.models.runtime import RuntimeLease

        count = 0
        for data in leases:
            try:
                lease = RuntimeLease(
                    app_instance_id=data["app_instance_id"],
                    status=data["status"],
                    health=data.get("health", "healthy"),
                    last_heartbeat_at=datetime.fromisoformat(data["last_heartbeat_at"]) if data.get("last_heartbeat_at") else datetime.now(UTC),
                    restart_count=data.get("restart_count", 0),
                )
                runtime_host._leases[lease.app_instance_id] = lease
                count += 1
            except Exception as e:
                logger.warning("Failed to restore lease for %s: %s", data.get("app_instance_id", "?"), e)
        return count

    def _restore_runtime_checkpoints(self, checkpoints: dict[str, list[dict]], runtime_host: Any) -> int:
        from app.models.runtime import RuntimeCheckpoint

        count = 0
        for app_id, cp_list in checkpoints.items():
            runtime_host._checkpoints.setdefault(app_id, [])
            for data in cp_list:
                try:
                    cp = RuntimeCheckpoint(
                        checkpoint_id=data["checkpoint_id"],
                        app_instance_id=data["app_instance_id"],
                        status=data["status"],
                        pending_tasks=data.get("pending_tasks", []),
                        metadata=data.get("metadata", {}),
                        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC),
                    )
                    runtime_host._checkpoints[app_id].append(cp)
                    count += 1
                except Exception as e:
                    logger.warning("Failed to restore checkpoint for %s: %s", app_id, e)
        return count

    def _restore_pending_tasks(self, tasks: dict[str, list[str]], runtime_host: Any) -> int:
        count = 0
        for app_id, task_list in tasks.items():
            runtime_host._pending_tasks.setdefault(app_id, [])
            for task in task_list:
                if task not in runtime_host._pending_tasks[app_id]:
                    runtime_host._pending_tasks[app_id].append(task)
                    count += 1
        return count

    def _restore_registry_entries(self, data: dict[str, Any], registry: Any) -> int:
        from app.models.app_blueprint import AppBlueprint
        from app.models.registry import AppRegistryEntry, AppReleaseRecord
        from app.models.runtime_policy import RuntimePolicy
        from app.models.app_profile import AppRuntimeProfile

        count = 0

        # Restore blueprints
        blueprints = data.get("blueprints", {})
        for bp_id, bp_data in blueprints.items():
            try:
                runtime_policy = RuntimePolicy(**bp_data.get("runtime_policy", {}))
                runtime_profile = AppRuntimeProfile(**bp_data.get("runtime_profile", {}))
                bp = AppBlueprint(
                    id=bp_data["id"],
                    name=bp_data["name"],
                    version=bp_data["version"],
                    goal=bp_data["goal"],
                    app_shape=bp_data["app_shape"],
                    required_skills=set(bp_data.get("required_skills", [])),
                    runtime_policy=runtime_policy,
                    runtime_profile=runtime_profile,
                )
                registry._blueprints[bp_id] = bp
                count += 1
            except Exception as e:
                logger.warning("Failed to restore blueprint %s: %s", bp_id, e)

        # Restore entries
        entries = data.get("entries", {})
        for eid, entry_data in entries.items():
            try:
                releases = []
                for r_data in entry_data.get("releases", []):
                    r = AppReleaseRecord(
                        version=r_data["version"],
                        status=r_data["status"],
                        note=r_data.get("note", ""),
                        reviewer=r_data.get("reviewer", ""),
                        app_shape=r_data.get("app_shape", ""),
                        required_skills=set(r_data.get("required_skills", [])),
                        runtime_policy=r_data.get("runtime_policy", {}),
                        runtime_profile=r_data.get("runtime_profile", {}),
                    )
                    if r_data.get("created_at"):
                        r.created_at = datetime.fromisoformat(r_data["created_at"])
                    if r_data.get("approved_at"):
                        r.approved_at = datetime.fromisoformat(r_data["approved_at"])
                    releases.append(r)

                runtime_profile = AppRuntimeProfile()
                entry = AppRegistryEntry(
                    blueprint_id=entry_data["blueprint_id"],
                    name=entry_data["name"],
                    version=entry_data["version"],
                    description=entry_data.get("description", ""),
                    release_status=entry_data.get("release_status", "active"),
                    app_shape=entry_data.get("app_shape", ""),
                    runtime_profile_summary=runtime_profile,
                    releases=releases,
                )
                if entry_data.get("approved_at"):
                    entry.approved_at = datetime.fromisoformat(entry_data["approved_at"])
                registry._entries[eid] = entry
                count += 1
            except Exception as e:
                logger.warning("Failed to restore registry entry %s: %s", eid, e)

        return count

    def _restore_catalog_entries(self, entries: list[dict], catalog: Any) -> int:
        from app.models.interaction import AppCatalogEntry

        count = 0
        for data in entries:
            try:
                entry = AppCatalogEntry(
                    app_id=data["app_id"],
                    name=data["name"],
                    description=data["description"],
                    execution_mode=data.get("execution_mode", "service"),
                    trigger_phrases=data.get("trigger_phrases", []),
                    blueprint_id=data["blueprint_id"],
                    version=data.get("version", "0.1.0"),
                )
                catalog.register(entry)
                count += 1
            except Exception as e:
                logger.warning("Failed to restore catalog entry %s: %s", data.get("app_id", "?"), e)
        return count

    def _restore_session_index(self, index: list[dict], memory: Any) -> int:
        """Restoring sessions is handled by LightBrainMemory's own _load_existing_sessions.
        This method is a no-op since session files persist independently."""
        return 0


def _json_default(obj: Any) -> Any:
    """Fallback JSON serializer for objects that aren't natively serializable."""
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, datetime):
        return _iso(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
