from __future__ import annotations

from types import SimpleNamespace

from app.runtime_paths import resolve_runtime_paths
from app.system.workers.app_mgmt import AppManagementWorker


def test_app_management_worker_launch_uses_install_model_data_dir_when_env_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    monkeypatch.delenv("AGENTSYSTEM_DATA_DIR", raising=False)

    captured = {}

    def fake_popen(cmd, stdout, stderr, env, cwd, start_new_session):
        captured["cwd"] = cwd
        return SimpleNamespace(pid=12345)

    monkeypatch.setattr("app.system.workers.app_mgmt.subprocess.Popen", fake_popen)

    worker = AppManagementWorker()
    pid = worker._launch_subprocess("echo", {})

    assert pid == 12345
    assert captured["cwd"] == str(resolve_runtime_paths().data_dir.resolve())
