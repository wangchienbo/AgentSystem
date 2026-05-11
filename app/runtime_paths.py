from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_AGENTSYSTEM_HOME_ENV = "AGENTSYSTEM_HOME"
DEFAULT_AGENTSYSTEM_CONFIG_DIR_ENV = "AGENTSYSTEM_CONFIG_DIR"
DEFAULT_AGENTSYSTEM_DATA_DIR_ENV = "AGENTSYSTEM_DATA_DIR"
DEFAULT_AGENTSYSTEM_STATE_DIR_ENV = "AGENTSYSTEM_STATE_DIR"
DEFAULT_AGENTSYSTEM_CACHE_DIR_ENV = "AGENTSYSTEM_CACHE_DIR"
DEFAULT_AGENTSYSTEM_LOG_DIR_ENV = "AGENTSYSTEM_LOG_DIR"
DEFAULT_AGENTSYSTEM_ASSET_DIR_ENV = "AGENTSYSTEM_ASSET_DIR"


@dataclass(frozen=True)
class RuntimePaths:
    repo_root: Path
    home_dir: Path
    config_dir: Path
    data_dir: Path
    state_dir: Path
    cache_dir: Path
    logs_dir: Path
    installed_assets_dir: Path
    build_dir: Path
    config_file: Path
    legacy_repo_installed_dir: Path
    legacy_repo_build_dir: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "repo_root": str(self.repo_root),
            "home_dir": str(self.home_dir),
            "config_dir": str(self.config_dir),
            "data_dir": str(self.data_dir),
            "state_dir": str(self.state_dir),
            "cache_dir": str(self.cache_dir),
            "logs_dir": str(self.logs_dir),
            "installed_assets_dir": str(self.installed_assets_dir),
            "build_dir": str(self.build_dir),
            "config_file": str(self.config_file),
            "legacy_repo_installed_dir": str(self.legacy_repo_installed_dir),
            "legacy_repo_build_dir": str(self.legacy_repo_build_dir),
        }


DEFAULT_HOME_FALLBACK = Path.home() / ".local" / "share" / "agentsystem"
DEFAULT_CONFIG_SUBDIR = "config"
DEFAULT_DATA_SUBDIR = "data"
DEFAULT_STATE_SUBDIR = "state"
DEFAULT_CACHE_SUBDIR = "cache"
DEFAULT_LOGS_SUBDIR = "logs"
DEFAULT_INSTALLED_ASSETS_SUBDIR = "assets" / Path("installed")
DEFAULT_BUILD_SUBDIR = "artifacts" / Path("build")
DEFAULT_CONFIG_FILENAME = "config.yaml"


def _path_from_env(name: str) -> Path | None:
    value = os.getenv(name)
    if not value:
        return None
    return Path(value).expanduser()


def resolve_runtime_paths(repo_root: Path | None = None) -> RuntimePaths:
    repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    home_dir = _path_from_env(DEFAULT_AGENTSYSTEM_HOME_ENV) or DEFAULT_HOME_FALLBACK
    config_dir = _path_from_env(DEFAULT_AGENTSYSTEM_CONFIG_DIR_ENV) or home_dir / DEFAULT_CONFIG_SUBDIR
    data_dir = _path_from_env(DEFAULT_AGENTSYSTEM_DATA_DIR_ENV) or home_dir / DEFAULT_DATA_SUBDIR
    state_dir = _path_from_env(DEFAULT_AGENTSYSTEM_STATE_DIR_ENV) or home_dir / DEFAULT_STATE_SUBDIR
    cache_dir = _path_from_env(DEFAULT_AGENTSYSTEM_CACHE_DIR_ENV) or home_dir / DEFAULT_CACHE_SUBDIR
    logs_dir = _path_from_env(DEFAULT_AGENTSYSTEM_LOG_DIR_ENV) or home_dir / DEFAULT_LOGS_SUBDIR
    installed_assets_dir = _path_from_env(DEFAULT_AGENTSYSTEM_ASSET_DIR_ENV) or home_dir / DEFAULT_INSTALLED_ASSETS_SUBDIR
    build_dir = home_dir / DEFAULT_BUILD_SUBDIR
    config_file = config_dir / DEFAULT_CONFIG_FILENAME

    return RuntimePaths(
        repo_root=repo_root,
        home_dir=home_dir,
        config_dir=config_dir,
        data_dir=data_dir,
        state_dir=state_dir,
        cache_dir=cache_dir,
        logs_dir=logs_dir,
        installed_assets_dir=installed_assets_dir,
        build_dir=build_dir,
        config_file=config_file,
        legacy_repo_installed_dir=repo_root / "installed",
        legacy_repo_build_dir=repo_root / "build",
    )
