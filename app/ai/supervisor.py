from __future__ import annotations

from datetime import UTC, datetime

from app.models.scheduling import SupervisionActionResult, SupervisionPolicy, SupervisionStatus
from app.services.runtime_host import AppRuntimeHostService, RuntimeHostError
from app.services.runtime_state_store import RuntimeStateStore


class SupervisorError(ValueError):
    pass


class SupervisorService:
    def __init__(self, runtime_host: AppRuntimeHostService, store: RuntimeStateStore | None = None) -> None:
        self._runtime_host = runtime_host
        self._policies: dict[str, SupervisionPolicy] = {}
        self._statuses: dict[str, SupervisionStatus] = {}
        self._store = store

    def register_policy(self, policy: SupervisionPolicy) -> SupervisionPolicy:
        self._runtime_host.get_overview(policy.app_instance_id)
        self._policies[policy.app_instance_id] = policy
        self._statuses.setdefault(policy.app_instance_id, SupervisionStatus(app_instance_id=policy.app_instance_id))
        self._persist()
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
            status.circuit_opened_at = datetime.now(UTC)
        elif policy.restart_on_failure and status.restart_attempts < policy.max_restart_attempts:
            status.state = "restart_pending"
        else:
            status.state = "healthy"
        self._persist()
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

        # In half_open, this is the probe test request
        probe_restart = status.state == "half_open"

        try:
            overview = self._runtime_host.get_overview(app_instance_id)
            current_status = overview.app_instance["status"]
            if current_status in {"failed", "stopped", "installed"}:
                self._runtime_host.start(app_instance_id, reason="supervisor restart")
        except RuntimeHostError as error:
            # Test request failed in half_open → back to circuit_open
            if probe_restart:
                status.state = "circuit_open"
                status.circuit_opened_at = datetime.now(UTC)
                status.updated_at = datetime.now(UTC)
                self._persist()
                return SupervisionActionResult(
                    app_instance_id=app_instance_id,
                    action="attempt_restart",
                    state="circuit_open",
                    failure_count=status.failure_count,
                    restart_attempts=status.restart_attempts,
                    message=f"probe restart failed, circuit re-opened: {error}",
                )
            raise SupervisorError(str(error)) from error

        status.restart_attempts += 1
        if probe_restart:
            # Probe test succeeded → back to healthy
            status.state = "healthy"
            status.circuit_opened_at = None
            msg = "probe restart succeeded, circuit recovered to healthy"
        else:
            status.state = "healthy"
            msg = "restart attempted"
        status.updated_at = datetime.now(UTC)
        self._persist()
        return SupervisionActionResult(
            app_instance_id=app_instance_id,
            action="attempt_restart",
            state=status.state,
            failure_count=status.failure_count,
            restart_attempts=status.restart_attempts,
            message=msg,
        )

    def reset(self, app_instance_id: str) -> SupervisionActionResult:
        status = self.get_status(app_instance_id)
        status.state = "healthy"
        status.failure_count = 0
        status.restart_attempts = 0
        status.last_failure_reason = ""
        status.circuit_opened_at = None
        status.updated_at = datetime.now(UTC)
        self._persist()
        return SupervisionActionResult(
            app_instance_id=app_instance_id,
            action="reset",
            state=status.state,
            failure_count=status.failure_count,
            restart_attempts=status.restart_attempts,
            message="supervision status reset",
        )

    def probe_circuit(self, app_instance_id: str) -> SupervisionActionResult:
        """Probe a circuit_open circuit to see if it has transitioned to half_open.

        If the circuit_breaker_timeout has elapsed, transition to half_open and
        allow one test restart. On success, return to healthy. On failure,
        return to circuit_open.
        """
        policy = self.get_policy(app_instance_id)
        status = self.get_status(app_instance_id)
        if status.state != "circuit_open":
            raise SupervisorError(
                f"Probe only applies to circuit_open state; current state: {status.state}: {app_instance_id}"
            )
        if status.circuit_opened_at is None:
            raise SupervisorError(f"Circuit opened_at not set: {app_instance_id}")

        timeout = policy.circuit_breaker_timeout
        elapsed = (datetime.now(UTC) - status.circuit_opened_at).total_seconds()
        if elapsed < timeout:
            remaining = timeout - elapsed
            raise SupervisorError(
                f"Circuit timeout not yet elapsed: {remaining:.0f}s remaining: {app_instance_id}"
            )

        # Timeout elapsed → transition to half_open and allow one test request
        status.state = "half_open"
        status.updated_at = datetime.now(UTC)
        self._persist()
        return SupervisionActionResult(
            app_instance_id=app_instance_id,
            action="probe_circuit",
            state="half_open",
            failure_count=status.failure_count,
            restart_attempts=status.restart_attempts,
            message=f"circuit transitioned to half_open after {timeout}s timeout",
        )

    def circuit_reset(self, app_instance_id: str) -> SupervisionActionResult:
        """Manually reset a circuit (circuit_open or half_open) back to healthy."""
        status = self.get_status(app_instance_id)
        if status.state not in {"circuit_open", "half_open"}:
            raise SupervisorError(
                f"Circuit reset only applies to circuit_open/half_open; current state: {status.state}: {app_instance_id}"
            )
        status.state = "healthy"
        status.circuit_opened_at = None
        status.updated_at = datetime.now(UTC)
        self._persist()
        return SupervisionActionResult(
            app_instance_id=app_instance_id,
            action="circuit_reset",
            state="healthy",
            failure_count=status.failure_count,
            restart_attempts=status.restart_attempts,
            message="circuit manually reset to healthy",
        )

    def _persist(self) -> None:
        if self._store is None:
            return
        self._store.save_mapping("supervision_policies", self._policies)
        self._store.save_mapping("supervision_statuses", self._statuses)
