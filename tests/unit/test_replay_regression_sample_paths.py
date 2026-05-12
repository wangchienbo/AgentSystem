from __future__ import annotations

from app.runtime_paths import resolve_runtime_paths
from app.system.replay_regression_samples import _ensure_store_dir


def test_replay_regression_sample_store_defaults_to_install_model_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))

    store_dir = _ensure_store_dir()

    assert store_dir == resolve_runtime_paths().data_dir / "replay_regression_samples"
