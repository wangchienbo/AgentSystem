from __future__ import annotations

from app.runtime_paths import resolve_runtime_paths
from app.system.workers.user_service import UserService


def test_user_service_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    service = UserService()

    assert service._users_dir == resolve_runtime_paths().data_dir / "users"
