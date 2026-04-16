"""App Rollback Service — safe rollback to a previous snapshot.

Rollback flow:
1. Pre-flight checks (snapshot exists, current state allows rollback)
2. Restore blueprint and runtime policy from snapshot
3. State transitions: upgrading → installed (or failed → installed)
4. Registry update
5. Rollback log recording via UpgradeLogEvent
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.app_instance import AppStatus
from app.models.runtime_policy import RuntimePolicy
from app.models.upgrade_log import UpgradeLogEvent
from app.services.upgrade_log_service import UpgradeLogService
from app.services.upgrade_service import UpgradeService, UpgradeSnapshot

logger = logging.getLogger(__name__)

# States from which rollback is allowed
_ROLLBACK_ALLOWED_STATES: set[AppStatus] = {"upgrading", "failed", "running", "installed", "paused", "stopped"}


class RollbackRequest(BaseModel):
    """Request payload for rolling back an app."""
    app_instance_id: str = Field(..., min_length=1)
    reviewer: str = Field(default="")
    reason: str = Field(default="")
    force: bool = Field(default=False)


class RollbackResult(BaseModel):
    """Result of a rollback operation."""
    app_instance_id: str
    from_version: str
    to_version: str
    previous_status: AppStatus
    final_status: AppStatus
    snapshot_restored: bool = True
    rollback_log_id: str = ""
    success: bool = True
    error: str = ""


class RollbackError(ValueError):
    pass


class RollbackService:
    """Manages safe app rollbacks from snapshots."""

    def __init__(
        self,
        upgrade_service: UpgradeService,
        log_service: UpgradeLogService,
    ) -> None:
        self._upgrade_service = upgrade_service
        self._log_service = log_service

    def rollback(
        self,
        app_instance_id: str,
        *,
        reviewer: str = "",
        reason: str = "",
        force: bool = False,
    ) -> RollbackResult:
        """Roll back an app instance to its pre-upgrade snapshot.

        Steps:
        1. Pre-flight checks (snapshot exists, state allows rollback)
        2. Restore blueprint and policy from snapshot
        3. Transition to installed state
        4. Record rollback log
        """
        from app.services.lifecycle import LifecycleError

        # ---- Pre-flight checks ----
        try:
            instance = self._upgrade_service._lifecycle.get_instance(app_instance_id)
        except LifecycleError as e:
            raise RollbackError(f"App instance not found: {app_instance_id}") from e

        if not force and instance.status not in _ROLLBACK_ALLOWED_STATES:
            raise RollbackError(
                f"Cannot rollback app {app_instance_id}: status '{instance.status}' "
                f"does not allow rollback. Allowed: {sorted(_ROLLBACK_ALLOWED_STATES)}. "
                f"Use force=True to override."
            )

        snapshot = self._upgrade_service.get_snapshot(app_instance_id)
        if snapshot is None:
            raise RollbackError(
                f"No rollback snapshot found for app {app_instance_id}. "
                f"Upgrade must be performed first to create a snapshot."
            )

        previous_status = instance.status
        from_version = instance.installed_version
        to_version = snapshot.installed_version

        # ---- Restore from snapshot ----
        try:
            self._restore_snapshot(snapshot, instance)

            # ---- Transition to installed ----
            if instance.status in {"upgrading", "failed"}:
                try:
                    self._upgrade_service._lifecycle.transition(
                        app_instance_id, "stop", reason=f"rollback: {reason or 'restored from snapshot'}"
                    )
                except LifecycleError:
                    # State transition may fail if already in a terminal state; set directly
                    logger.warning(
                        "State transition failed for %s during rollback; setting status directly",
                        app_instance_id,
                    )
                    instance.status = "installed"

            logger.info(
                "Rollback completed for %s: v%s (%s) → v%s (%s)",
                app_instance_id,
                from_version,
                previous_status,
                to_version,
                instance.status,
            )
        except Exception as e:
            logger.error("Rollback failed for %s: %s", app_instance_id, e)
            return RollbackResult(
                app_instance_id=app_instance_id,
                from_version=from_version,
                to_version=to_version,
                previous_status=previous_status,
                final_status=instance.status,
                snapshot_restored=False,
                success=False,
                error=str(e),
            )

        # ---- Record rollback log ----
        log_event = UpgradeLogEvent(
            event_id=f"rollback:{app_instance_id}:{to_version}",
            event_type="app_rollback",
            scope="app",
            app_id=app_instance_id,
            payload={
                "from_version": from_version,
                "to_version": to_version,
                "previous_status": previous_status,
                "reviewer": reviewer,
                "reason": reason,
                "snapshot_id": f"snapshot:{app_instance_id}",
                "force": force,
            },
        )
        self._log_service.append_event("app_upgrades", log_event)

        return RollbackResult(
            app_instance_id=app_instance_id,
            from_version=from_version,
            to_version=to_version,
            previous_status=previous_status,
            final_status=instance.status,
            snapshot_restored=True,
            rollback_log_id=log_event.event_id,
        )

    def _restore_snapshot(self, snapshot: UpgradeSnapshot, instance: Any) -> None:
        """Restore an instance from a snapshot, updating both the instance and the snapshot record."""
        instance.installed_version = snapshot.installed_version
        instance.runtime_policy = RuntimePolicy(**snapshot.runtime_policy)

        # Restore resolved skills from snapshot
        if "resolved_skills" in snapshot.instance:
            instance.resolved_skills = snapshot.instance["resolved_skills"]
        if "system_skills" in snapshot.instance:
            instance.system_skills = snapshot.instance["system_skills"]

        # Update the registry blueprint if available
        self._update_registry_blueprint(snapshot)

    def _update_registry_blueprint(self, snapshot: UpgradeSnapshot) -> None:
        """Update the registry with the rolled-back blueprint."""
        try:
            from app.api.main import app_registry
            from app.models.app_blueprint import AppBlueprint

            bp_data = snapshot.blueprint
            if bp_data:
                bp = AppBlueprint.model_validate(bp_data)
                app_registry._blueprints[snapshot.blueprint_id] = bp
        except Exception as e:
            logger.warning("Failed to update registry blueprint during rollback: %s", e)

    def get_rollback_history(self, app_instance_id: str) -> list[UpgradeLogEvent]:
        """Retrieve rollback log events for an app instance."""
        all_events = self._upgrade_service.get_upgrade_log(app_instance_id)
        return [e for e in all_events if e.event_type == "app_rollback"]
