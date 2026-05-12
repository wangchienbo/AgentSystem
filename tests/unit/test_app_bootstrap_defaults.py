from __future__ import annotations

from app.runtime.app_bootstrap import run_app_bootstrap
from app.runtime_paths import resolve_runtime_paths


def test_app_bootstrap_uses_install_model_runtime_paths_when_data_dir_omitted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    class _StopLoop(Exception):
        pass

    def fake_sleep(_seconds: int) -> None:
        raise _StopLoop

    monkeypatch.setattr("app.runtime.app_bootstrap.time.sleep", fake_sleep)
    monkeypatch.setattr("app.runtime.app_bootstrap.signal.signal", lambda *_args, **_kwargs: None)

    try:
        run_app_bootstrap("app.demo")
    except _StopLoop:
        pass

    runtime_file = resolve_runtime_paths().data_dir / "runtime_center.json"
    assert runtime_file.exists()
