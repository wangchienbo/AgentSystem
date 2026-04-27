from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from app.bootstrap.runtime import build_runtime
from app.services.regression_nightly_control import (
    REGRESSION_NIGHTLY_SCHEDULE_ID,
    RegressionNightlyControlService,
)


def build_service(tmp_path: Path) -> RegressionNightlyControlService:
    services = build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )
    return RegressionNightlyControlService(
        scheduler=services["scheduler"],
        runtime_host=services["runtime_host"],
        runtime_store=services["runtime_store"],
        refinement_memory=services["refinement_memory"],
    )


def test_build_nightly_status_exposes_due_state(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    record = service.register_nightly_schedule(interval_seconds=3600)
    record.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)

    status = service.build_nightly_status({"running": False})

    assert status["registered"] is True
    assert status["due_now"] is True
    assert REGRESSION_NIGHTLY_SCHEDULE_ID in status["due_schedule_ids"]
    assert status["automation_control"]["schedule_registered"] is True


def test_trigger_due_tick_skips_when_not_due(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)

    result = service.trigger_due_tick(client=Mock(), driver_status={"running": False})

    assert result["triggered"] is False
    assert result["nightly_status"]["last_tick_decision"] == "skipped_not_due"


def test_trigger_due_tick_executes_when_due(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    record = service.register_nightly_schedule(interval_seconds=3600)
    record.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)
    service.run_cycle = Mock(return_value={"run_id": "svc-nightly-run"})

    result = service.trigger_due_tick(client=Mock(), driver_status={"running": True})

    assert result["triggered"] is True
    assert result["cycle"]["run_id"] == "svc-nightly-run"
    assert result["nightly_status"]["last_tick_decision"] == "triggered_due"


def test_trigger_manual_cycle_returns_not_triggered_when_scheduler_no_match(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    result = service.trigger_manual_cycle(client=Mock())
    assert result["triggered"] is False
    assert isinstance(result["schedule_results"], list)


def test_trigger_manual_cycle_executes_and_clears_pending_when_schedule_matches(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)
    service.run_cycle = Mock(return_value={"run_id": "manual-run-1"})

    result = service.trigger_manual_cycle(client=Mock())

    assert result["triggered"] is True
    assert result["cycle"]["run_id"] == "manual-run-1"


def test_build_nightly_status_exposes_automation_control_card(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)

    status = service.build_nightly_status({"running": True, "interval_seconds": 60})

    assert "automation_control" in status
    assert status["automation_control"]["driver"]["running"] is True
    assert status["automation_control"]["schedule_registered"] is True
    assert status["automation_control"]["last_tick_outcome"] == "skipped"


def test_trigger_due_tick_records_no_trigger_match(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    record = service.register_nightly_schedule(interval_seconds=3600)
    record.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)
    service._scheduler.trigger_interval_schedules = Mock(return_value=[])

    result = service.trigger_due_tick(client=Mock(), driver_status={"running": False})

    assert result["triggered"] is False
    assert result["nightly_status"]["last_tick_decision"] == "skipped_no_trigger_match"


def test_trigger_due_tick_propagates_cycle_failure_and_records_failed_state(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    record = service.register_nightly_schedule(interval_seconds=3600)
    record.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)

    def _boom(client):
        raise RuntimeError("cycle failed")

    service.run_cycle = _boom

    try:
        service.trigger_due_tick(client=Mock(), driver_status={"running": True})
    except RuntimeError as exc:
        assert str(exc) == "cycle failed"
    else:
        raise AssertionError("expected RuntimeError")

    state = service.load_tick_state()
    assert state["last_tick_decision"] == "failed_cycle"
    assert state["last_cycle_result"]["error_type"] == "RuntimeError"


def test_build_nightly_status_exposes_failure_fields_in_automation_control(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)
    service.save_tick_state({
        "last_tick_at": "2026-04-28T00:00:00Z",
        "last_tick_decision": "failed_cycle",
        "last_tick_triggered": False,
        "last_cycle_result": {"error": "cycle failed", "error_type": "RuntimeError"},
    })

    status = service.build_nightly_status({"running": False})

    assert status["automation_control"]["last_tick_outcome"] == "failed"
    assert status["automation_control"]["last_cycle_error"] == "cycle failed"
    assert status["automation_control"]["last_cycle_error_type"] == "RuntimeError"
