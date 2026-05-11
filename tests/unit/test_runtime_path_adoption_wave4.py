from __future__ import annotations

from app.orchestration.core_orchestrator import CoreOrchestrator
from app.runtime_paths import resolve_runtime_paths


def test_core_orchestrator_defaults_to_resolved_data_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    orchestrator = CoreOrchestrator()
    assert orchestrator._data_dir == str(resolve_runtime_paths().data_dir)
