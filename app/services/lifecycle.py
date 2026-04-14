from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.app_instance import AppInstance, AppStatus
from app.models.runtime import LifecycleEvent, LifecycleTransitionResult
from app.models.upgrade_log import UpgradeLogEvent
from app.services.runtime_state_store import RuntimeStateStore


class LifecycleError(ValueError):
    pass


_ALLOWED_TRANSITIONS: dict[AppStatus, set[AppStatus]] = {
    "draft": {"validating", "archived"},
    "validating": {"compiled", "draft", "archived"},
    "compiled": {"installed", "draft", "archived"},
    "installed": {"running", "upgrading", "archived"},
    "running": {"paused", "stopped", "failed", "upgrading", "archived"},
    "paused": {"running", "stopped", "failed", "archived"},
    "stopped": {"running", "archived"},
    "failed": {"stopped", "running", "archived"},
    "upgrading": {"running", "failed", "stopped", "installed", "archived"},
    "archived": set(),
}

_EVENT_TO_TARGET: dict[str, AppStatus] = {
    "validate": "validating",
    "compile": "compiled",
    "install": "installed",
    "start": "running",
    "pause": "paused",
    "resume": "running",
    "stop": "stopped",
    "fail": "failed",
    "upgrade": "upgrading",
    "archive": "archived",
}


class AppLifecycleService:
    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self._instances: dict[str, AppInstance] = {}
        self._events: dict[str, list[LifecycleEvent]] = {}
        self._store = store

        # Asset registration hooks — set by runtime bootstrap
        self._on_asset_start_fn = None  # called after start → running
        self._on_asset_stop_fn = None   # called after stop/fail

    def set_asset_hooks(self, on_asset_start=None, on_asset_stop=None) -> None:
        """Set callbacks for asset self-registration.
        
        on_asset_start: (app_instance_id) -> None
        on_asset_stop: (app_instance_id) -> None
        """
        self._on_asset_start_fn = on_asset_start
        self._on_asset_stop_fn = on_asset_stop

    def register_instance(self, instance: AppInstance) -> AppInstance:
        self._instances[instance.id] = instance
        self._events.setdefault(instance.id, [])
        self._persist()
        return instance

    def get_instance(self, app_instance_id: str) -> AppInstance:
        if app_instance_id not in self._instances:
            raise LifecycleError(f"App instance not found: {app_instance_id}")
        return self._instances[app_instance_id]

    def list_instances(self) -> list[AppInstance]:
        return list(self._instances.values())

    def list_events(self, app_instance_id: str) -> list[LifecycleEvent]:
        self.get_instance(app_instance_id)
        return list(self._events.get(app_instance_id, []))

    def transition(self, app_instance_id: str, event: str, reason: str = "") -> LifecycleTransitionResult:
        instance = self.get_instance(app_instance_id)
        if event not in _EVENT_TO_TARGET:
            raise LifecycleError(f"Unsupported lifecycle event: {event}")
        target = _EVENT_TO_TARGET[event]
        if target not in _ALLOWED_TRANSITIONS[instance.status]:
            raise LifecycleError(
                f"Invalid lifecycle transition for {app_instance_id}: {instance.status} -> {target}"
            )

        previous_status = instance.status
        instance.status = target
        self._events[app_instance_id].append(
            LifecycleEvent(
                app_instance_id=app_instance_id,
                event_type=event,  # type: ignore[arg-type]
                from_status=previous_status,
                to_status=target,
                reason=reason,
            )
        )
        self._persist()

        # Asset self-registration hooks
        if target == "running" and self._on_asset_start_fn:
            try:
                self._on_asset_start_fn(app_instance_id)
            except Exception as e:
                logger.warning("Asset start hook failed for %s: %s", app_instance_id, e)
        elif target in ("stopped", "failed") and self._on_asset_stop_fn:
            try:
                self._on_asset_stop_fn(app_instance_id)
            except Exception as e:
                logger.warning("Asset stop hook failed for %s: %s", app_instance_id, e)

        return LifecycleTransitionResult(
            app_instance_id=app_instance_id,
            previous_status=previous_status,
            current_status=target,
            event=event,  # type: ignore[arg-type]
            recorded_events=len(self._events[app_instance_id]),
        )

    # ------------------------------------------------------------------
    # Archive / Unarchive
    # ------------------------------------------------------------------

    _ARCHIVE_ALLOWED: set[AppStatus] = {"installed", "stopped", "failed"}

    def archive(self, app_instance_id: str, *, reason: str = "") -> LifecycleTransitionResult:
        instance = self.get_instance(app_instance_id)
        if instance.status not in self._ARCHIVE_ALLOWED:
            raise LifecycleError(
                f"Cannot archive app {app_instance_id}: current status '{instance.status}' "
                f"is not one of {sorted(self._ARCHIVE_ALLOWED)}"
            )
        previous_status = instance.status
        # Save archive snapshot
        snapshot = self._build_archive_snapshot(instance)
        self._store_snapshot(app_instance_id, snapshot)
        # Transition to archived
        instance.status = "archived"
        self._events[app_instance_id].append(
            LifecycleEvent(
                app_instance_id=app_instance_id,
                event_type="archive",
                from_status=previous_status,
                to_status="archived",
                reason=reason,
            )
        )
        self._persist()
        self._log_archive_event(app_instance_id, "archive", previous_status, snapshot)
        return LifecycleTransitionResult(
            app_instance_id=app_instance_id,
            previous_status=previous_status,
            current_status="archived",
            event="archive",
            recorded_events=len(self._events[app_instance_id]),
        )

    def unarchive(self, app_instance_id: str, *, reason: str = "") -> LifecycleTransitionResult:
        instance = self.get_instance(app_instance_id)
        if instance.status != "archived":
            raise LifecycleError(
                f"Cannot unarchive app {app_instance_id}: current status is '{instance.status}', expected 'archived'"
            )
        # Restore from snapshot if available
        snapshot = self._load_snapshot(app_instance_id)
        if snapshot is not None:
            instance.installed_version = snapshot.get("installed_version", instance.installed_version)
            instance.system_skills = snapshot.get("system_skills", instance.system_skills)
            instance.resolved_skills = snapshot.get("resolved_skills", instance.resolved_skills)
            instance.execution_mode = snapshot.get("execution_mode", instance.execution_mode)
            instance.data_namespace = snapshot.get("data_namespace", instance.data_namespace)
        previous_status = instance.status
        instance.status = "installed"
        self._events[app_instance_id].append(
            LifecycleEvent(
                app_instance_id=app_instance_id,
                event_type="archive",  # same event type, direction indicated by from/to
                from_status=previous_status,
                to_status="installed",
                reason=reason,
            )
        )
        self._persist()
        self._log_archive_event(app_instance_id, "unarchive", previous_status, snapshot)
        return LifecycleTransitionResult(
            app_instance_id=app_instance_id,
            previous_status=previous_status,
            current_status="installed",
            event="archive",
            recorded_events=len(self._events[app_instance_id]),
        )

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _build_archive_snapshot(self, instance: AppInstance) -> dict:
        return {
            "app_instance_id": instance.id,
            "blueprint_id": instance.blueprint_id,
            "owner_user_id": instance.owner_user_id,
            "status": instance.status,
            "installed_version": instance.installed_version,
            "data_namespace": instance.data_namespace,
            "execution_mode": instance.execution_mode,
            "system_skills": list(instance.system_skills),
            "resolved_skills": list(instance.resolved_skills),
            "archived_at": datetime.now(UTC).isoformat(),
        }

    def _store_snapshot(self, app_instance_id: str, snapshot: dict) -> None:
        if self._store is None:
            return
        snapshots = self._store.load_json("archive_snapshots", {})
        snapshots[app_instance_id] = snapshot
        self._store._write_json("archive_snapshots", snapshots)

    def _load_snapshot(self, app_instance_id: str) -> dict | None:
        if self._store is None:
            return None
        snapshots = self._store.load_json("archive_snapshots", {})
        return snapshots.get(app_instance_id)

    def _log_archive_event(
        self,
        app_instance_id: str,
        action: str,
        from_status: AppStatus,
        snapshot: dict | None,
    ) -> None:
        """Append an archive/unarchive event to the upgrade log."""
        try:
            upgrade_log_base = Path("data/runtime/upgrade_logs")
            upgrade_log_base.mkdir(parents=True, exist_ok=True)
            stream_path = upgrade_log_base / "lifecycle"
            stream_path.mkdir(parents=True, exist_ok=True)
            today = datetime.now(UTC).date().isoformat()
            file_path = stream_path / f"{today}.jsonl"
            event = UpgradeLogEvent(
                event_id=f"{action}:{app_instance_id}:{datetime.now(UTC).isoformat()}",
                event_type=f"app_{action}",
                scope="lifecycle",
                app_id=app_instance_id,
                payload={
                    "action": action,
                    "from_status": from_status,
                    "snapshot": snapshot,
                },
            )
            with file_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
        except OSError:
            pass  # Best-effort logging

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("app_instances", self._instances)
        self._store.save_nested_mapping("lifecycle_events", self._events)
