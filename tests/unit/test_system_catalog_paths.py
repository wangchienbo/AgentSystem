from __future__ import annotations

from app.runtime_paths import resolve_runtime_paths
from app.system.catalog.system_catalog import SystemCatalog


def test_system_catalog_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    catalog = SystemCatalog()

    assert catalog._catalog_path == resolve_runtime_paths().data_dir / "system_catalog.json"
