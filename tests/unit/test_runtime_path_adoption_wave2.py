from __future__ import annotations

from app.persistence.persistence_service import PersistenceService
from app.runtime_paths import resolve_runtime_paths
from app.orchestration.pipeline_executor import _default_workspace


def test_persistence_service_defaults_to_resolved_state_persistence_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    service = PersistenceService()
    assert service._data_dir == resolve_runtime_paths().state_dir / "persistence"


def test_pipeline_executor_default_workspace_uses_resolved_data_dir(monkeypatch) -> None:
    monkeypatch.delenv("AGENTSYSTEM_DATA_DIR", raising=False)
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    assert _default_workspace() == str(resolve_runtime_paths().data_dir.resolve())


def test_pipeline_executor_default_workspace_prefers_explicit_data_env(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_DATA_DIR", "/tmp/custom-data")
    assert _default_workspace() == "/tmp/custom-data"
