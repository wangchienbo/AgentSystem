from __future__ import annotations

from pathlib import Path

from app.cli import run_cli
from app.runtime_paths import resolve_runtime_paths
from tests.unit.bootstrap_test_helper import build_runtime_for_bootstrap_tests


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_layout_and_bootstrap_remain_repo_cwd_independent(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "agentsystem-home"
    outside_cwd = tmp_path / "outside-cwd"
    outside_cwd.mkdir()

    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.chdir(outside_cwd)

    layout = run_cli(["runtime-layout"])
    bootstrap = run_cli(["bootstrap"])
    expected = resolve_runtime_paths(REPO_ROOT)

    assert layout.details["installed_assets_dir"] == str(expected.installed_assets_dir)
    assert layout.details["build_dir"] == str(expected.build_dir)
    assert bootstrap.details["repo_overlap"] == {}
    assert Path(str(bootstrap.details["home_dir"])).exists()
    assert str(outside_cwd) not in str(layout.details["installed_assets_dir"])
    assert str(outside_cwd) not in str(layout.details["build_dir"])


def test_build_runtime_keeps_assets_and_persistence_outside_repo(monkeypatch, tmp_path: Path) -> None:
    outside_cwd = tmp_path / "outside-cwd"
    outside_cwd.mkdir()
    monkeypatch.chdir(outside_cwd)

    services = build_runtime_for_bootstrap_tests(tmp_path)
    runtime_paths = resolve_runtime_paths(REPO_ROOT)
    asset_center = services["asset_center"]
    runtime_center = services["runtime_center"]

    assert asset_center._installed_dir == runtime_paths.installed_assets_dir
    assert asset_center._build_dir == runtime_paths.build_dir
    assert runtime_center._data_file == runtime_paths.state_dir / "runtime_center.json"
    assert REPO_ROOT not in asset_center._installed_dir.parents
    assert REPO_ROOT not in asset_center._build_dir.parents
    assert REPO_ROOT not in runtime_center._data_file.parents
    assert outside_cwd not in asset_center._installed_dir.parents
    assert outside_cwd not in asset_center._build_dir.parents
    assert outside_cwd not in runtime_center._data_file.parents
