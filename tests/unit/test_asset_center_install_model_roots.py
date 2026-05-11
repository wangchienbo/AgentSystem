from __future__ import annotations

from pathlib import Path

from app.runtime_paths import resolve_runtime_paths
from app.system.catalog.asset_center import AssetCenter


def test_asset_center_defaults_to_resolved_install_model_roots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    asset_center = AssetCenter(source_dir=str(tmp_path / "source"))
    paths = resolve_runtime_paths()

    assert asset_center._source_dir == tmp_path / "source"
    assert asset_center._installed_dir == paths.installed_assets_dir
    assert asset_center._build_dir == paths.build_dir
    assert asset_center._data_dir == paths.data_dir
