from __future__ import annotations

from pathlib import Path

from app.bootstrap.runtime import describe_phase6_asset_bootstrap_binding
from app.runtime_paths import resolve_runtime_paths
from tests.unit.bootstrap_test_helper import build_runtime_for_bootstrap_tests


def test_build_runtime_keeps_current_bootstrap_binding_under_isolated_config(tmp_path: Path) -> None:
    services = build_runtime_for_bootstrap_tests(tmp_path)
    startup_state = services["startup_state"]
    runtime_paths = resolve_runtime_paths(Path(__file__).resolve().parents[2])
    binding = describe_phase6_asset_bootstrap_binding(Path(__file__).resolve().parents[2])
    preview = describe_phase6_asset_bootstrap_binding(
        Path(__file__).resolve().parents[2],
        installed_assets_mode="install-model-preview",
    )

    assert startup_state["ready_stages"] == [
        "asset_center",
        "entrypoints",
        "interaction_runtime",
        "model_runtime",
        "system_assets",
    ]
    assert binding["installed_dir"].endswith("/installed")
    assert preview["installed_dir"] == str(runtime_paths.installed_assets_dir)
    assert binding["installed_dir"] != preview["installed_dir"]
    assert binding["runtime_registry_file"].endswith("/data/runtime_center.json")
    assert preview["runtime_registry_file"] == binding["runtime_registry_file"]
