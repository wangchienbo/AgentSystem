from __future__ import annotations

from app.persistence.runtime_state_store import RuntimeStateStore
from app.persistence.upgrade_log_service import UpgradeLogService
from app.runtime_paths import resolve_runtime_paths
from app.system.catalog.resource_center import ResourceCenter
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.runtime.app_data_store import AppDataStore
from app.system.runtime.config_center import ConfigCenterService


def test_runtime_state_store_defaults_to_resolved_state_runtime_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    store = RuntimeStateStore()
    assert store.base_path == resolve_runtime_paths().state_dir / "runtime"


def test_app_data_store_defaults_to_resolved_data_namespaces_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    store = AppDataStore()
    assert store.base_path == resolve_runtime_paths().data_dir / "namespaces"


def test_upgrade_log_service_defaults_to_resolved_upgrade_log_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    service = UpgradeLogService()
    assert service.base_path == resolve_runtime_paths().state_dir / "runtime" / "upgrade_logs"


def test_runtime_center_defaults_to_resolved_state_file(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    center = RuntimeCenter()
    assert center._data_file == resolve_runtime_paths().state_dir / "runtime_center.json"


def test_resource_center_defaults_to_resolved_data_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    center = ResourceCenter()
    assert center._data_dir == resolve_runtime_paths().data_dir
    assert center._config.resource_store_path == "resources.json"


def test_config_center_defaults_to_resolved_data_dir(monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", "/tmp/agentsystem-home")
    service = ConfigCenterService()
    assert service._data_dir == resolve_runtime_paths().data_dir
