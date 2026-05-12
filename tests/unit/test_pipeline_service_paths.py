from __future__ import annotations

from app.orchestration.pipeline_service import PipelineService
from app.runtime_paths import resolve_runtime_paths


def test_pipeline_service_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    service = PipelineService()

    assert service._base_dir == resolve_runtime_paths().data_dir / "pipelines"
