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
