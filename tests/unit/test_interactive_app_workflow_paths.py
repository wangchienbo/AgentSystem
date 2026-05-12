from __future__ import annotations

from app.interactive_app_workflow import InteractiveAppWorkflow
from app.runtime_paths import resolve_runtime_paths


def test_interactive_app_workflow_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    workflow = InteractiveAppWorkflow()

    assert workflow._workflow_dir == resolve_runtime_paths().data_dir / "interactive_app" / "workflows"
