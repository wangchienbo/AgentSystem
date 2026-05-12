from __future__ import annotations

from app.runtime_paths import resolve_runtime_paths
from app.services.context_storage_paths import build_context_storage_paths


def test_build_context_storage_paths_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    paths = build_context_storage_paths()

    assert paths.base_dir == resolve_runtime_paths().data_dir / "context_center"
