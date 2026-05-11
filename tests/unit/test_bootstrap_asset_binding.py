from __future__ import annotations

from pathlib import Path

from app.bootstrap.runtime import describe_phase6_asset_bootstrap_binding
from app.runtime_paths import resolve_runtime_paths


def test_describe_phase6_asset_bootstrap_binding_reports_transition_contract(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    binding = describe_phase6_asset_bootstrap_binding(repo_root)
    runtime_paths = resolve_runtime_paths(repo_root)

    assert binding["source_dir"] == str(repo_root / "source")
    assert binding["installed_dir"] == str(repo_root / "installed")
    assert binding["build_dir"] == str(repo_root / "build")
    assert binding["data_dir"] == str(runtime_paths.data_dir)
    assert binding["runtime_registry_file"] == str(repo_root / "data" / "runtime_center.json")
    assert binding["binding_mode"] == "repo_pinned_assets_with_install_model_data"


def test_describe_phase6_asset_bootstrap_binding_preview_reports_install_model_asset_roots(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    binding = describe_phase6_asset_bootstrap_binding(repo_root, installed_assets_mode="install-model-preview")
    runtime_paths = resolve_runtime_paths(repo_root)

    assert binding["source_dir"] == str(repo_root / "source")
    assert binding["installed_dir"] == str(runtime_paths.installed_assets_dir)
    assert binding["build_dir"] == str(runtime_paths.build_dir)
    assert binding["runtime_registry_file"] == str(repo_root / "data" / "runtime_center.json")
    assert binding["binding_mode"] == "install_model_asset_preview_with_repo_source"
