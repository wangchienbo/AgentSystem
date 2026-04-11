"""Enhanced circuit-breaker tests: half_open, probe_circuit, circuit_reset."""

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from tests.unit.api_test_helper import create_isolated_test_client

from app.models.app_instance import AppInstance
from app.models.scheduling import SupervisionPolicy
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService, RuntimeHostError
from app.services.supervisor import SupervisorError, SupervisorService


def build_instance() -> AppInstance:
    return AppInstance(
        id="app.cb.001",
        blueprint_id="bp.cb.001",
        owner_user_id="user.cb",
        status="installed",
        data_namespace="tenant/cb/app.cb.001",
    )


def test_probe_circuit_transitions_to_half_open_after_timeout() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.cb.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.cb.001",
            app_instance_id="app.cb.001",
            max_restart_attempts=5,
            open_circuit_after_failures=2,
            circuit_breaker_timeout=1,  # 1 second for fast tests
        )
    )

    # Trigger circuit_open
    runtime.mark_failed("app.cb.001", reason="boom-1")
    supervisor.observe_failure("app.cb.001", reason="boom-1")
    runtime.stop("app.cb.001")
    runtime.start("app.cb.001")
    runtime.mark_failed("app.cb.001", reason="boom-2")
    result = supervisor.observe_failure("app.cb.001", reason="boom-2")
    assert result.state == "circuit_open"

    # Probe before timeout → should fail
    try:
        supervisor.probe_circuit("app.cb.001")
    except SupervisorError as error:
        assert "not yet elapsed" in str(error)
    else:
        raise AssertionError("expected SupervisorError for probe before timeout")

    # Wait for timeout

    time.sleep(1.1)

    # Probe after timeout → half_open
    result = supervisor.probe_circuit("app.cb.001")
    assert result.state == "half_open"
    assert "half_open" in result.message


def test_probe_circuit_non_open_state_fails() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.cb.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.cb.002",
            app_instance_id="app.cb.001",
            open_circuit_after_failures=2,
            circuit_breaker_timeout=1,
        )
    )

    # Not circuit_open yet
    try:
        supervisor.probe_circuit("app.cb.001")
    except SupervisorError as error:
        assert "current state" in str(error)
    else:
        raise AssertionError("expected SupervisorError for non-circuit_open probe")


def test_half_open_probe_restart_succeeds_recovery_to_healthy() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.cb.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.cb.003",
            app_instance_id="app.cb.001",
            max_restart_attempts=5,
            open_circuit_after_failures=2,
            circuit_breaker_timeout=1,
        )
    )

    # Circuit open
    runtime.mark_failed("app.cb.001", reason="fail-1")
    supervisor.observe_failure("app.cb.001", reason="fail-1")
    runtime.stop("app.cb.001")
    runtime.start("app.cb.001")
    runtime.mark_failed("app.cb.001", reason="fail-2")
    supervisor.observe_failure("app.cb.001", reason="fail-2")
    assert supervisor.get_status("app.cb.001").state == "circuit_open"


    time.sleep(1.1)

    # Probe → half_open
    probe = supervisor.probe_circuit("app.cb.001")
    assert probe.state == "half_open"

    # Restart while half_open → should succeed and go to healthy
    result = supervisor.attempt_restart("app.cb.001")
    assert result.state == "healthy"
    assert "recovered to healthy" in result.message


def test_circuit_reset_manually_resets_open_circuit() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.cb.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.cb.004",
            app_instance_id="app.cb.001",
            open_circuit_after_failures=1,
            circuit_breaker_timeout=60,
        )
    )

    runtime.mark_failed("app.cb.001", reason="crash")
    supervisor.observe_failure("app.cb.001", reason="crash")
    assert supervisor.get_status("app.cb.001").state == "circuit_open"

    result = supervisor.circuit_reset("app.cb.001")
    assert result.state == "healthy"
    assert result.action == "circuit_reset"
    assert supervisor.get_status("app.cb.001").circuit_opened_at is None


def test_circuit_reset_on_healthy_fails() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.cb.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.cb.005",
            app_instance_id="app.cb.001",
            open_circuit_after_failures=3,
        )
    )

    try:
        supervisor.circuit_reset("app.cb.001")
    except SupervisorError as error:
        assert "current state" in str(error)
    else:
        raise AssertionError("expected SupervisorError")


def test_reset_clears_circuit_opened_at() -> None:
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.cb.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.cb.006",
            app_instance_id="app.cb.001",
            open_circuit_after_failures=1,
        )
    )

    runtime.mark_failed("app.cb.001")
    supervisor.observe_failure("app.cb.001")
    assert supervisor.get_status("app.cb.001").circuit_opened_at is not None

    supervisor.reset("app.cb.001")
    assert supervisor.get_status("app.cb.001").circuit_opened_at is None


def test_half_open_probe_restart_failure_re_opens_circuit() -> None:
    """When a probe restart fails (RuntimeHostError), circuit should re-open."""
    lifecycle = AppLifecycleService()
    runtime = AppRuntimeHostService(lifecycle=lifecycle)
    supervisor = SupervisorService(runtime_host=runtime)
    runtime.register_instance(build_instance())
    runtime.start("app.cb.001")
    supervisor.register_policy(
        SupervisionPolicy(
            policy_id="sup.cb.007",
            app_instance_id="app.cb.001",
            max_restart_attempts=5,
            open_circuit_after_failures=2,
            circuit_breaker_timeout=1,
        )
    )

    # Circuit open
    runtime.mark_failed("app.cb.001", reason="f1")
    supervisor.observe_failure("app.cb.001", reason="f1")
    runtime.stop("app.cb.001")
    runtime.start("app.cb.001")
    runtime.mark_failed("app.cb.001", reason="f2")
    supervisor.observe_failure("app.cb.001", reason="f2")
    assert supervisor.get_status("app.cb.001").state == "circuit_open"


    time.sleep(1.1)

    # Probe → half_open
    supervisor.probe_circuit("app.cb.001")
    assert supervisor.get_status("app.cb.001").state == "half_open"

    # Simulate a RuntimeHostError during restart by patching get_overview
    original_get_overview = runtime.get_overview

    def failing_overview(app_id: str):
        raise RuntimeHostError("simulated runtime error")

    runtime.get_overview = failing_overview  # type: ignore

    result = supervisor.attempt_restart("app.cb.001")
    assert result.state == "circuit_open"
    assert "probe restart failed" in result.message
    assert "circuit re-opened" in result.message

    # Restore
    runtime.get_overview = original_get_overview  # type: ignore


def test_circuit_breaker_timeout_default_value() -> None:
    policy = SupervisionPolicy(
        policy_id="sup.cb.008",
        app_instance_id="app.cb.001",
        open_circuit_after_failures=3,
    )
    assert policy.circuit_breaker_timeout == 300  # default 5 minutes


def test_probe_circuit_api_flow(tmp_path: Path) -> None:
    """Test probe-circuit and circuit-reset endpoints via the main app."""
    from app.api.main import app
    with TestClient(app) as client:
        client.post(
            "/apps",
            json={
                "id": "app.cb.api.001",
                "blueprint_id": "bp.cb.api.001",
                "owner_user_id": "user.cb.api",
                "status": "draft",
                "data_namespace": "tenant/cb-api/app.cb.api.001",
            },
        )
        client.post("/apps/app.cb.api.001/actions/validate", json={})
        client.post("/apps/app.cb.api.001/actions/compile", json={})
        client.post("/apps/app.cb.api.001/actions/install", json={})
        client.post("/apps/app.cb.api.001/actions/start", json={})

        # Register policy with short timeout
        client.post(
            "/supervision/policies",
            json={
                "policy_id": "sup.cb.api.001",
                "app_instance_id": "app.cb.api.001",
                "max_restart_attempts": 5,
                "open_circuit_after_failures": 1,
                "circuit_breaker_timeout": 1,
            },
        )

        # Trigger circuit_open
        client.post("/apps/app.cb.api.001/actions/fail", json={"reason": "api fail"})
        observe = client.post("/supervision/app.cb.api.001/observe-failure", json={"reason": "api fail"})
        assert observe.json()["state"] == "circuit_open"

        # Probe before timeout → 400 (SupervisorError maps to 400)
        probe = client.post("/supervision/app.cb.api.001/probe-circuit")
        assert probe.status_code == 400

        import time
        time.sleep(1.1)

        # Probe after timeout → 200
        probe = client.post("/supervision/app.cb.api.001/probe-circuit")
        assert probe.status_code == 200
        assert probe.json()["state"] == "half_open"

        # Circuit reset → 200
        reset_r = client.post("/supervision/app.cb.api.001/circuit-reset")
        assert reset_r.status_code == 200
        assert reset_r.json()["state"] == "healthy"
