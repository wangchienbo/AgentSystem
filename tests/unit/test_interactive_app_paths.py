from __future__ import annotations

from app.interactive_app import InteractiveAppService
from app.runtime_paths import resolve_runtime_paths


def test_interactive_app_service_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    service = InteractiveAppService()

    assert service._base_dir == resolve_runtime_paths().data_dir / "interactive_app"
