from __future__ import annotations

import pytest

from app.system.startup.startup_orchestrator import (
    StartupOrchestrator,
    StartupOrchestratorError,
    StartupStage,
)


def test_startup_orchestrator_executes_stages_in_dependency_order() -> None:
    order: list[str] = []
    orchestrator = StartupOrchestrator()

    orchestrator.add_stage(StartupStage(name="asset_center", action=lambda: order.append("asset_center") or {"ok": True}))
    orchestrator.add_stage(StartupStage(name="model_runtime", depends_on=("asset_center",), action=lambda: order.append("model_runtime") or {"ok": True}))
    orchestrator.add_stage(StartupStage(name="system_assets", depends_on=("model_runtime",), action=lambda: order.append("system_assets") or {"ok": True}))

    results = orchestrator.execute()

    assert [item.name for item in results] == ["asset_center", "model_runtime", "system_assets"]
    assert order == ["asset_center", "model_runtime", "system_assets"]
    assert orchestrator.ready_stages() == {"asset_center", "model_runtime", "system_assets"}


def test_startup_orchestrator_fails_fast_when_dependency_missing() -> None:
    orchestrator = StartupOrchestrator()
    orchestrator.add_stage(StartupStage(name="system_assets", depends_on=("asset_center",), action=lambda: {"ok": True}))

    with pytest.raises(StartupOrchestratorError):
        orchestrator.execute()


def test_startup_orchestrator_fails_fast_on_required_stage_error() -> None:
    orchestrator = StartupOrchestrator()
    orchestrator.add_stage(StartupStage(name="asset_center", action=lambda: {"ok": True}))
    orchestrator.add_stage(StartupStage(name="model_runtime", depends_on=("asset_center",), action=lambda: (_ for _ in ()).throw(ValueError("probe failed"))))

    with pytest.raises(StartupOrchestratorError):
        orchestrator.execute()

    results = orchestrator.results()
    assert results[-1].name == "model_runtime"
    assert results[-1].status == "failed"
    assert results[-1].detail["error_type"] == "ValueError"


def test_startup_orchestrator_can_rerun_failed_stage_after_fix() -> None:
    orchestrator = StartupOrchestrator()
    state = {"ok": False}

    orchestrator.add_stage(StartupStage(name="asset_center", action=lambda: {"ok": True}))
    orchestrator.add_stage(
        StartupStage(
            name="system_assets",
            depends_on=("asset_center",),
            action=lambda: {"registered_assets": 0 if not state["ok"] else 3},
            ready_check=lambda detail: (
                detail["registered_assets"] >= 3,
                {"reason": "missing required assets" if detail["registered_assets"] < 3 else "ok", "fully_ready": detail["registered_assets"] >= 3},
            ),
        )
    )

    with pytest.raises(StartupOrchestratorError):
        orchestrator.execute()

    state["ok"] = True
    recovered = orchestrator.rerun_stage("system_assets")

    assert recovered.status == "ready"
    assert recovered.detail["recovered"] is True
    assert recovered.detail["fully_ready"] is True
    assert "system_assets" in orchestrator.ready_stages()


