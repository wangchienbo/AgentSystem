from __future__ import annotations

from datetime import UTC, datetime

from app.models.app_instance import AppInstance
from app.models.runtime import RuntimeCheckpoint, RuntimeLease, RuntimeOverview
from app.services.lifecycle import AppLifecycleService, LifecycleError


class RuntimeHostError(ValueError):
    pass


class AppRuntimeHostService:
    def __init__(self, lifecycle: AppLifecycleService) -> None:
        self._lifecycle = lifecycle
        self._leases: dict[str, RuntimeLease] = {}
        self._checkpoints: dict[str, list[RuntimeCheckpoint]] = {}
        self._pending_tasks: dict[str, list[str]] = {}

    def register_instance(self, instance: AppInstance) -> AppInstance:
        self._lifecycle.register_instance(instance)
        self._checkpoints.setdefault(instance.id, [])
        self._pending_tasks.setdefault(instance.id, [])
        return instance

    def start(self, app_instance_id: str, reason: str = "") -> RuntimeOverview:
        instance = self._lifecycle.get_instance(app_instance_id)
        result = self._lifecycle.transition(app_instance_id, "start", reason=reason)
        lease = RuntimeLease(app_instance_id=app_instance_id, status=result.current_status)
        self._leases[app_instance_id] = lease
        self._checkpoint(app_instance_id, "runtime.start")
        return self.get_overview(app_instance_id)

    def pause(self, app_instance_id: str, reason: str = "") -> RuntimeOverview:
        result = self._lifecycle.transition(app_instance_id, "pause", reason=reason)
        lease = self._require_lease(app_instance_id)
        lease.status = result.current_status
        lease.health = "degraded"
        lease.last_heartbeat_at = datetime.now(UTC)
        self._checkpoint(app_instance_id, "runtime.pause")
        return self.get_overview(app_instance_id)

    def resume(self, app_instance_id: str, reason: str = "") -> RuntimeOverview:
        result = self._lifecycle.transition(app_instance_id, "resume", reason=reason)
        lease = self._require_lease(app_instance_id)
        lease.status = result.current_status
        lease.health = "healthy"
        lease.last_heartbeat_at = datetime.now(UTC)
        self._checkpoint(app_instance_id, "runtime.resume")
        return self.get_overview(app_instance_id)

    def stop(self, app_instance_id: str, reason: str = "") -> RuntimeOverview:
        result = self._lifecycle.transition(app_instance_id, "stop", reason=reason)
        lease = self._require_lease(app_instance_id)
        lease.status = result.current_status
        lease.last_heartbeat_at = datetime.now(UTC)
        self._checkpoint(app_instance_id, "runtime.stop")
        return self.get_overview(app_instance_id)

    def mark_failed(self, app_instance_id: str, reason: str = "") -> RuntimeOverview:
        result = self._lifecycle.transition(app_instance_id, "fail", reason=reason)
        lease = self._require_lease(app_instance_id)
        lease.status = result.current_status
        lease.health = "failed"
        lease.last_heartbeat_at = datetime.now(UTC)
        self._checkpoint(app_instance_id, "runtime.fail", extra_metadata={"reason": reason})
        return self.get_overview(app_instance_id)

    def healthcheck(self, app_instance_id: str, healthy: bool = True) -> RuntimeLease:
        lease = self._require_lease(app_instance_id)
        lease.last_heartbeat_at = datetime.now(UTC)
        if healthy:
            lease.health = "healthy"
        else:
            lease.health = "failed"
            lease.restart_count += 1
        return lease

    def enqueue_task(self, app_instance_id: str, task_name: str) -> list[str]:
        self._lifecycle.get_instance(app_instance_id)
        tasks = self._pending_tasks.setdefault(app_instance_id, [])
        tasks.append(task_name)
        return list(tasks)

    def get_overview(self, app_instance_id: str) -> RuntimeOverview:
        instance = self._lifecycle.get_instance(app_instance_id)
        checkpoints = self._checkpoints.get(app_instance_id, [])
        return RuntimeOverview(
            app_instance={
                "id": instance.id,
                "status": instance.status,
                "blueprint_id": instance.blueprint_id,
                "owner_user_id": instance.owner_user_id,
            },
            lease=self._leases.get(app_instance_id),
            latest_checkpoint=checkpoints[-1] if checkpoints else None,
            pending_tasks=list(self._pending_tasks.get(app_instance_id, [])),
        )

    def _checkpoint(
        self,
        app_instance_id: str,
        checkpoint_id: str,
        extra_metadata: dict[str, str] | None = None,
    ) -> RuntimeCheckpoint:
        instance = self._lifecycle.get_instance(app_instance_id)
        checkpoint = RuntimeCheckpoint(
            checkpoint_id=f"{checkpoint_id}:{len(self._checkpoints[app_instance_id]) + 1}",
            app_instance_id=app_instance_id,
            status=instance.status,
            pending_tasks=list(self._pending_tasks.get(app_instance_id, [])),
            metadata=extra_metadata or {},
        )
        self._checkpoints[app_instance_id].append(checkpoint)
        return checkpoint

    def _require_lease(self, app_instance_id: str) -> RuntimeLease:
        if app_instance_id not in self._leases:
            raise RuntimeHostError(f"Runtime lease not found: {app_instance_id}")
        return self._leases[app_instance_id]
