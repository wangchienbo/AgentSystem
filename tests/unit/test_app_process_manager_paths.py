from __future__ import annotations

from app.runtime_paths import resolve_runtime_paths
from app.system.runtime.app_process_manager import AppProcessManager


def test_app_process_manager_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    manager = AppProcessManager()

    assert manager._data_dir == resolve_runtime_paths().data_dir
