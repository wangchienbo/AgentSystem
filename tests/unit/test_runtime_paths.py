from __future__ import annotations

from pathlib import Path

from app.runtime_paths import resolve_runtime_paths


def test_resolve_runtime_paths_defaults_to_standard_install_layout(monkeypatch) -> None:
    monkeypatch.delenv("AGENTSYSTEM_HOME", raising=False)
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.delenv("AGENTSYSTEM_DATA_DIR", raising=False)
    monkeypatch.delenv("AGENTSYSTEM_STATE_DIR", raising=False)
    monkeypatch.delenv("AGENTSYSTEM_CACHE_DIR", raising=False)
    monkeypatch.delenv("AGENTSYSTEM_LOG_DIR", raising=False)
    monkeypatch.delenv("AGENTSYSTEM_ASSET_DIR", raising=False)

    repo_root = Path("/tmp/agentsystem-repo")
    paths = resolve_runtime_paths(repo_root)

    assert paths.home_dir == Path.home() / ".local" / "share" / "agentsystem"
    assert paths.config_dir == paths.home_dir / "config"
    assert paths.data_dir == paths.home_dir / "data"
    assert paths.state_dir == paths.home_dir / "state"
    assert paths.cache_dir == paths.home_dir / "cache"
    assert paths.logs_dir == paths.home_dir / "logs"
    assert paths.installed_assets_dir == paths.home_dir / "assets" / "installed"
    assert paths.build_dir == paths.home_dir / "artifacts" / "build"
    assert paths.config_file == paths.config_dir / "config.yaml"
    assert paths.legacy_repo_installed_dir == repo_root / "installed"


def test_resolve_runtime_paths_honors_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/runtime/home")
    monkeypatch.setenv("AGENTSYSTEM_CONFIG_DIR", "/runtime/config")
    monkeypatch.setenv("AGENTSYSTEM_DATA_DIR", "/runtime/data")
    monkeypatch.setenv("AGENTSYSTEM_STATE_DIR", "/runtime/state")
    monkeypatch.setenv("AGENTSYSTEM_CACHE_DIR", "/runtime/cache")
    monkeypatch.setenv("AGENTSYSTEM_LOG_DIR", "/runtime/logs")
    monkeypatch.setenv("AGENTSYSTEM_ASSET_DIR", "/runtime/assets-installed")

    paths = resolve_runtime_paths(Path("/repo"))

    assert paths.home_dir == Path("/runtime/home")
    assert paths.config_dir == Path("/runtime/config")
    assert paths.data_dir == Path("/runtime/data")
    assert paths.state_dir == Path("/runtime/state")
    assert paths.cache_dir == Path("/runtime/cache")
    assert paths.logs_dir == Path("/runtime/logs")
    assert paths.installed_assets_dir == Path("/runtime/assets-installed")
