"""App Upgrade Service — safe, auditable blueprint upgrade flow.

Handles the full upgrade lifecycle:
1. Pre-flight checks (instance state, blueprint validation, dependency compat)
2. Snapshot current state for rollback
3. State transitions: installed/running → upgrading → installed
4. Blueprint & registry updates
5. Upgrade log recording via UpgradeLogEvent
"""

from __future__ import annotations

import copy
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.app_blueprint import AppBlueprint
from app.models.app_instance import AppInstance, AppStatus
from app.models.runtime_policy import RuntimePolicy
from app.models.upgrade_log import UpgradeLogEvent
from app.services.blueprint_compare import BlueprintCompareResult, BlueprintCompareService
from app.services.lifecycle import AppLifecycleService, LifecycleError
from app.services.upgrade_log_service import UpgradeLogService

logger = logging.getLogger(__name__)

# States that block an upgrade
_BLOCKED_STATES: set[AppStatus] = {"failed", "archived", "draft"}

# States that are allowed to initiate an upgrade
_ALLOWED_STATES: set[AppStatus] = {"installed", "running", "paused", "stopped", "upgrading"}


class UpgradeSnapshot(BaseModel):
    """Point-in-time snapshot of an app instance for rollback."""
    app_instance_id: str
    blueprint_id: str
    blueprint: dict[str, Any]
    instance: dict[str, Any]
    runtime_policy: dict[str, Any]
    installed_version: str
    status: AppStatus
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UpgradeRequest(BaseModel):
    """Request payload for upgrading an app."""
    blueprint_id: str = Field(..., min_length=1)
    reviewer: str = Field(default="")
    reason: str = Field(default="")
    skip_compare: bool = Field(default=False)
    require_reviewer: bool = Field(default=False)


class UpgradeResult(BaseModel):
    """Result of an upgrade operation."""
    app_instance_id: str
    blueprint_id: str
    from_version: str
    to_version: str
    previous_status: AppStatus
    final_status: AppStatus
    snapshot_id: str
    compare_summary: dict[str, Any] = Field(default_factory=dict)
    upgrade_log_id: str = ""
    success: bool = True
    error: str = ""


class UpgradeError(ValueError):
    pass


class UpgradeService:
    """Manages safe app upgrades with snapshots, state transitions, and logging."""

    def __init__(
        self,
        lifecycle: AppLifecycleService,
        log_service: UpgradeLogService,
        compare_service: BlueprintCompareService | None = None,
        runtime_center: Any = None,
        asset_center: Any = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._log_service = log_service
        self._compare = compare_service or BlueprintCompareService()
        self._runtime_center = runtime_center
        self._asset_center = asset_center
        # Snapshots keyed by app_instance_id (only the latest kept per instance)
        self._snapshots: dict[str, UpgradeSnapshot] = {}

    def get_snapshot(self, app_instance_id: str) -> UpgradeSnapshot | None:
        """Retrieve the latest snapshot for an app instance."""
        return self._snapshots.get(app_instance_id)

    def list_snapshots(self) -> dict[str, UpgradeSnapshot]:
        """Return all active snapshots."""
        return dict(self._snapshots)

    def upgrade(
        self,
        app_instance_id: str,
        new_blueprint: AppBlueprint,
        *,
        reviewer: str = "",
        reason: str = "",
        skip_compare: bool = False,
        require_reviewer: bool = False,
    ) -> UpgradeResult:
        """Execute a safe upgrade of an app instance to a new blueprint.

        Steps:
        1. Pre-flight checks (state, reviewer, blueprint, dependency compat)
        2. Capture snapshot
        3. Compare blueprints (unless skipped)
        4. Transition to "upgrading"
        5. Apply new blueprint and runtime policy
        6. Transition to "installed"
        7. Record upgrade log
        """
        # ---- Pre-flight checks ----
        instance = self._lifecycle.get_instance(app_instance_id)

        if instance.status in _BLOCKED_STATES:
            raise UpgradeError(
                f"Cannot upgrade app {app_instance_id}: status '{instance.status}' is blocked. "
                f"Allowed states: {sorted(_ALLOWED_STATES)}"
            )

        if require_reviewer and not reviewer:
            raise UpgradeError("Upgrade requires a reviewer but none was provided")

        if new_blueprint.id != instance.blueprint_id:
            raise UpgradeError(
                f"Blueprint ID mismatch: instance has '{instance.blueprint_id}', "
                f"upgrade blueprint has '{new_blueprint.id}'"
            )

        # Dependency compatibility: new required skills shouldn't be a strict subset
        # removal of all skills would be caught by compare risk, but we do a quick check
        old_skills = set(instance.resolved_skills)
        new_skills = set(new_blueprint.required_skills)
        if not new_skills and old_skills and not instance.system_skills:
            raise UpgradeError("New blueprint removes all required skills — incompatible")

        # Blueprint validation
        self._validate_blueprint(new_blueprint)

        # ---- Compare blueprints ----
        compare_summary: dict[str, Any] = {}
        if not skip_compare:
            registry_bp = self._get_registry_blueprint(instance.blueprint_id)
            if registry_bp is not None:
                compare_result = self._compare.compare(registry_bp, new_blueprint)
                compare_summary = {
                    "total_changes": compare_result.total_changes,
                    "risk_level": compare_result.risk_level,
                    "breaking_changes": compare_result.breaking_changes,
                    "summary": compare_result.summary,
                }
                logger.info(
                    "Blueprint compare for %s: %s",
                    app_instance_id,
                    compare_result.summary,
                )

        # ---- Capture snapshot ----
        from_version = instance.installed_version
        snapshot = self._capture_snapshot(instance)

        # ---- Transition to upgrading ----
        previous_status = instance.status
        self._lifecycle.transition(app_instance_id, "upgrade", reason=reason or f"Upgrading to v{new_blueprint.version}")

        # ---- Apply new blueprint and policy ----
        try:
            instance.installed_version = new_blueprint.version
            instance.runtime_policy = new_blueprint.runtime_policy.model_copy(deep=True)

            # Update resolved skills (merge system skills + new required skills)
            system_skills = set(instance.system_skills)
            all_skills = list(dict.fromkeys([*instance.system_skills, *new_blueprint.required_skills]))
            instance.resolved_skills = all_skills

            # ---- Transition to installed (from upgrading) ----
            # After upgrade, go to 'installed' state
            self._lifecycle.transition(app_instance_id, "stop", reason="upgrade_complete")

            logger.info(
                "Upgrade completed for %s: %s → %s",
                app_instance_id,
                previous_status,
                instance.status,
            )
        except Exception as e:
            # Partial failure — try to restore snapshot
            logger.error("Upgrade failed for %s, attempting rollback: %s", app_instance_id, e)
            self._restore_from_snapshot(snapshot)
            raise UpgradeError(f"Upgrade failed: {e}") from e

        # ---- Sync RuntimeCenter ----
        self._sync_runtime_upgrade(app_instance_id, from_version, new_blueprint.version)

        # ---- Record upgrade log ----
        log_event = UpgradeLogEvent(
            event_id=f"upgrade:{app_instance_id}:{new_blueprint.version}",
            event_type="app_upgrade",
            scope="app",
            app_id=app_instance_id,
            payload={
                "from_version": snapshot.installed_version,
                "to_version": new_blueprint.version,
                "previous_status": previous_status,
                "reviewer": reviewer,
                "reason": reason,
                "compare_summary": compare_summary,
                "snapshot_id": f"snapshot:{app_instance_id}",
            },
        )
        day = log_event.ts.date().isoformat()
        self._log_service.append_event("app_upgrades", log_event)

        return UpgradeResult(
            app_instance_id=app_instance_id,
            blueprint_id=new_blueprint.id,
            from_version=snapshot.installed_version,
            to_version=new_blueprint.version,
            previous_status=previous_status,
            final_status=instance.status,
            snapshot_id=f"snapshot:{app_instance_id}",
            compare_summary=compare_summary,
            upgrade_log_id=log_event.event_id,
        )

    def get_upgrade_log(self, app_instance_id: str) -> list[UpgradeLogEvent]:
        """Retrieve upgrade log events for an app instance."""
        # Read from the most recent day first, then search backwards
        all_events: list[UpgradeLogEvent] = []
        from datetime import timedelta
        today = datetime.now(UTC).date()
        for i in range(30):  # search last 30 days
            day_str = (today - timedelta(days=i)).isoformat()
            events = self._log_service.read_events("app_upgrades", day_str)
            matching = [e for e in events if e.app_id == app_instance_id]
            all_events.extend(matching)
        return sorted(all_events, key=lambda e: e.ts, reverse=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _capture_snapshot(self, instance: AppInstance) -> UpgradeSnapshot:
        """Capture a point-in-time snapshot of an app instance."""
        bp = self._get_registry_blueprint(instance.blueprint_id)
        bp_data = bp.model_dump(mode="json") if bp else {}

        snapshot = UpgradeSnapshot(
            app_instance_id=instance.id,
            blueprint_id=instance.blueprint_id,
            blueprint=bp_data,
            instance=instance.model_dump(mode="json"),
            runtime_policy=instance.runtime_policy.model_dump(mode="json"),
            installed_version=instance.installed_version,
            status=instance.status,
        )
        self._snapshots[instance.id] = snapshot
        logger.info("Snapshot captured for %s (v%s, status=%s)", instance.id, instance.installed_version, instance.status)
        return snapshot

    def _restore_from_snapshot(self, snapshot: UpgradeSnapshot) -> None:
        """Restore an app instance from a snapshot."""
        try:
            instance = self._lifecycle.get_instance(snapshot.app_instance_id)
            instance.installed_version = snapshot.installed_version
            instance.runtime_policy = RuntimePolicy(**snapshot.runtime_policy)
            instance.status = snapshot.status
            logger.info("Restored %s from snapshot to v%s (status=%s)", instance.id, snapshot.installed_version, snapshot.status)
        except Exception as e:
            logger.error("Failed to restore %s from snapshot: %s", snapshot.app_instance_id, e)

    def _validate_blueprint(self, blueprint: AppBlueprint) -> None:
        """Basic blueprint validation before upgrade."""
        if not blueprint.id or not blueprint.name:
            raise UpgradeError("Blueprint must have a valid id and name")
        if not blueprint.version:
            raise UpgradeError("Blueprint must have a version")

    def _get_registry_blueprint(self, blueprint_id: str) -> AppBlueprint | None:
        """Try to get blueprint from registry."""
        try:
            from app.api.main import app_registry
            return app_registry.get_blueprint(blueprint_id)
        except Exception:
            return None

    def _sync_runtime_upgrade(self, app_instance_id: str, from_version: str, to_version: str) -> None:
        """Sync upgrade to RuntimeCenter and AssetCenter."""
        if self._runtime_center:
            entry = self._runtime_center.get(app_instance_id)
            if entry:
                self._runtime_center.register(
                    asset_id=entry.asset_id,
                    version=to_version,
                    pid=entry.pid,
                    endpoint=entry.endpoint,
                    owner=entry.owner,
                )
        if self._asset_center:
            installed_version = self._asset_center.get_installed_version(app_instance_id)
            if installed_version and installed_version != to_version:
                try:
                    self._asset_center.install(app_instance_id)
                except Exception:
                    pass  # Non-blocking: AssetCenter may not have this asset
