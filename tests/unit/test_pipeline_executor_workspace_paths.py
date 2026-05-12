from __future__ import annotations

import asyncio

from app.orchestration.pipeline_executor import ExecutorType, PipelineExecutor, PipelineStep
from app.runtime_paths import resolve_runtime_paths


def test_pipeline_executor_user_workspace_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    executor = PipelineExecutor(workspace=str(tmp_path / "workspace"))
    step = PipelineStep(step_id="s1", executor_type=ExecutorType.SHELL, command="echo ok")

    asyncio.run(executor.execute_pipeline([step], user_id="u1"))

    expected = resolve_runtime_paths().data_dir / "users" / "u1" / "workspace"
    for item in executor.executors.values():
        assert item.workspace == str(expected)
