from __future__ import annotations

from datetime import UTC, datetime

from app.models.scheduling import SupervisionActionResult, SupervisionPolicy, SupervisionStatus
from app.services.runtime_host import AppRuntimeHostService, RuntimeHostError


class SupervisorError(ValueError):
    pass


class SupervisorService:
    def __init__(self, runtime_host: AppRuntimeHostService) -> None:
        self._runtime_host = runtime_host
        self._policies: dict[str, SupervisionPolicy] = {}
        self._statuses: dict[str, SupervisionStatus] = {}

    def register_policy(self, policy: SupervisionPolicy) -> SupervisionPolicy:
        self._runtime_host.get_overview(policy.app_instance_id)
        self._policies[policy.app_instance_id] = policy
        self._statuses.setdefault(policy.app_instance_id, SupervisionStatus(app_instance_id=policy.app_instance_id))
        return policy

    def get_policy(self, app_instance_id: str) -> SupervisionPolicy:
        if app_instance_id not in self._policies:
            raise SupervisorError(f"Supervision policy not found: {app_instance_id}")
        return self._policies[app_instance_id]

    def get_status(self, app_instance_id: str) -> SupervisionStatus:
        if app_instance_id not in self._statuses:
            raise SupervisorError(f"Supervision status not found: {app_instance_id}")
        return self._statuses[app_instance_id]

    def observe_failure(self, app_instance_id: str, reason: str = "") -> SupervisionActionResult:
        policy = self.get_policy(app_instance_id)
        status = self.get_status(app_instance_id)
        status.failure_count += 1
        status.last_failure_reason = reason
        status.updated_at = datetime.now(UTC)
        if status.failure_count >= policy.open_circuit_after_failures:
            status.state = "circuit_open"
        elif policy.restart_on_failure and status.restart_attempts < policy.max_restart_attempts:
            status.state = "restart_pending"
        else:
            status.state = "healthy"
        return SupervisionActionResult(
            app_instance_id=app_instance_id,
            action="observe_failure",
            state=status.state,
            failure_count=status.failure_count,
            restart_attempts=status.restart_attempts,
            message=reason,
        )

    def attempt_restart(self, app_instance_id: str) -> SupervisionActionResult:
        policy = self.get_policy(app_instance_id)
        status = self.get_status(app_instance_id)
        if status.state == "circuit_open":
            raise SupervisorError(f"Restart blocked by open circuit: {app_instance_id}")
        if not policy.restart_on_failure:
            raise SupervisorError(f"Restart disabled by policy: {app_instance_id}")
        if status.restart_attempts >= policy.max_restart_attempts:
            raise SupervisorError(f"Restart attempts exceeded: {app_instance_id}")

        try:
            overview = self._runtime_host.get_overview(app_instance_id)
            current_status = overview.app_instance["status"]
            if current_status in {"failed", "stopped", "installed"}:
                self._runtime_host.start(app_instance_id, reason="supervisor restart")
        except RuntimeHostError as error:
            raise SupervisorError(str(error)) from error

        status.restart_attempts += 1
        status.state = "healthy"
        status.updated_at = datetime.now(UTC)
        return SupervisionActionResult(
            app_instance_id=app_instance_id,
            action="attempt_restart",
            state=status.state,
            failure_count=status.failure_count,
            restart_attempts=status.restart_attempts,
            message="restart attempted",
        )

    def reset(self, app_instance_id: str) -> SupervisionActionResult:
        status = self.get_status(app_instance_id)
        status.state = "healthy"
        status.failure_count = 0
        status.restart_attempts = 0
        status.last_failure_reason = ""
        status.updated_at = datetime.now(UTC)
        return SupervisionActionResult(
            app_instance_id=app_instance_id,
            action="reset",
            state=status.state,
            failure_count=status.failure_count,
            restart_attempts=status.restart_attempts,
            message="supervision status reset",
        )
