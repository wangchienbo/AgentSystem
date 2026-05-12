from __future__ import annotations

from pathlib import Path

from app.cli import build_parser, run_cli
from app.runtime_paths import resolve_runtime_paths

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_build_parser_supports_phase1_command_surface() -> None:
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    assert "start" in choices
    assert "stop" in choices
    assert "restart" in choices
    assert "status" in choices
    assert "install" in choices
    assert "bootstrap" in choices
    assert "doctor" in choices
    assert "runtime-layout" in choices
    assert "migrate-runtime" in choices
    assert "assets" in choices


def test_run_cli_returns_status_contract_for_top_level_command() -> None:
    result = run_cli(["status"])
    expected = resolve_runtime_paths(REPO_ROOT)
    assert result.command == "status"
    assert result.details["status"] in {"ok", "needs_attention"}
    assert str(result.details["repo_root"]) == str(REPO_ROOT)
    assert result.details["operation_scope"] == "resolved_runtime_health_view"
    assert result.details["status_reason"] in {"all_transition_checks_passed", "missing_transition_prerequisites"}
    assert isinstance(result.details["missing_checks"], list)
    assert "service_reachable" in result.details
    assert str(result.details["config_file"]) == str(expected.config_file)


def test_run_cli_returns_not_implemented_contract_for_start() -> None:
    result = run_cli(["start"])
    assert result.command == "start"
    assert result.exit_code == 2
    assert result.details["status"] == "not_implemented"
    assert result.details["operation_scope"] == "installed_runtime_target_not_yet_wired"
    assert "next_step" in result.details
    assert "--app-dir" in str(result.details["suggested_start_command"])
    assert "AGENTSYSTEM_DATA_DIR=" in str(result.details["suggested_start_command"])
    assert "-m uvicorn app.system.http_test_server:app" in str(result.details["suggested_start_command"])


def test_run_cli_returns_runtime_layout_contract() -> None:
    result = run_cli(["runtime-layout"])
    expected = resolve_runtime_paths(REPO_ROOT)
    assert result.command == "runtime-layout"
    assert result.details["status"] == "ok"
    assert result.details["layout_mode"] == "transition_install_model_ready"
    assert result.details["operation_scope"] == "resolved_runtime_layout_view"
    assert str(result.details["config_dir"]) == str(expected.config_dir)
    assert str(result.details["installed_assets_dir"]) == str(expected.installed_assets_dir)
    transition = result.details["asset_root_transition"]
    assert isinstance(transition, dict)
    assert transition["installed_runtime_assets"] == str(expected.installed_assets_dir)
    assert transition["legacy_repo_installed"] == str(REPO_ROOT / "installed")
    assert transition["bootstrap_status"] == "install_model_asset_roots_live_repo_source_retained"
    bootstrap_binding = result.details["bootstrap_asset_binding"]
    assert isinstance(bootstrap_binding, dict)
    assert bootstrap_binding["installed_dir"] == str(expected.installed_assets_dir)
    assert bootstrap_binding["build_dir"] == str(expected.build_dir)
    assert bootstrap_binding["binding_mode"] == "install_model_asset_preview_with_repo_source"
    bootstrap_preview = result.details["bootstrap_asset_binding_preview"]
    assert isinstance(bootstrap_preview, dict)
    assert bootstrap_preview["installed_dir"] == str(REPO_ROOT / "installed")
    assert bootstrap_preview["build_dir"] == str(REPO_ROOT / "build")
    assert bootstrap_preview["binding_mode"] == "repo_pinned_assets_with_install_model_data"


def test_run_cli_returns_doctor_checks() -> None:
    result = run_cli(["doctor"])
    assert result.command == "doctor"
    assert result.details["status"] in {"ok", "needs_attention"}
    assert result.details["operation_scope"] == "resolved_runtime_health_view"
    assert result.details["status_reason"] in {"all_transition_checks_passed", "missing_transition_prerequisites"}
    assert isinstance(result.details["missing_checks"], list)
    checks = result.details["checks"]
    assert isinstance(checks, dict)
    assert "config_dir" in checks
    assert "data_dir" in checks
    assert "state_dir" in checks
    assert "config_file" in checks
    assert "service_reachable" in checks
    assert isinstance(result.details["next_actions"], list)
    assert "suggested_start_command" in result.details


def test_run_cli_bootstrap_initializes_runtime_layout_and_seeds_legacy_config(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "agentsystem-home"
    legacy_home = tmp_path / "legacy-home"
    legacy_config = legacy_home / ".config" / "agentsystem" / "config.yaml"
    legacy_config.parent.mkdir(parents=True, exist_ok=True)
    legacy_config.write_text("models: {}\n", encoding="utf-8")

    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: legacy_home)

    result = run_cli(["bootstrap"])
    expected = resolve_runtime_paths(REPO_ROOT)

    assert result.command == "bootstrap"
    assert result.details["status"] == "ok"
    assert result.details["operation_scope"] == "runtime_layout_initialization"
    assert str(result.details["config_file"]) == str(expected.config_file)
    assert result.details["config_status"] == "seeded_from_legacy"
    assert Path(str(result.details["config_file"])).read_text(encoding="utf-8") == "models: {}\n"
    assert str(expected.build_dir) in result.details["created_dirs"]
    assert result.details["repo_overlap"] == {}


def test_run_cli_migrate_runtime_reports_legacy_paths_and_repo_overlap(monkeypatch, tmp_path: Path) -> None:
    repo_runtime_home = REPO_ROOT / "tmp-runtime-home-test"
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(repo_runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    legacy_runtime_center = REPO_ROOT / "data" / "runtime_center.json"
    legacy_runtime_center.parent.mkdir(parents=True, exist_ok=True)
    legacy_runtime_center.write_text("{}\n", encoding="utf-8")
    try:
        result = run_cli(["migrate-runtime"])
    finally:
        legacy_runtime_center.unlink(missing_ok=True)
        if repo_runtime_home.exists():
            import shutil
            shutil.rmtree(repo_runtime_home, ignore_errors=True)

    assert result.command == "migrate-runtime"
    assert result.details["status"] == "ok"
    assert result.details["operation_scope"] == "runtime_migration_audit"
    assert result.details["migration_status"] == "attention_needed"
    found = result.details["found_legacy_paths"]
    assert "legacy_repo_runtime_center" in found
    overlap = result.details["repo_overlap"]
    assert "build_dir" in overlap
    assert result.details["warnings"]
    assert result.details["next_actions"]


    start_wrapper = (REPO_ROOT / "start_server.sh").read_text(encoding="utf-8")
    stop_wrapper = (REPO_ROOT / "stop_server.sh").read_text(encoding="utf-8")
    start_web_wrapper = (REPO_ROOT / "start_web_server.sh").read_text(encoding="utf-8")
    assert "app/cli.py\" start" in start_wrapper
    assert "app/cli.py\" stop" in stop_wrapper
    assert "app/cli.py\" start" in start_web_wrapper


def test_run_cli_supports_assets_list_command() -> None:
    result = run_cli(["assets", "list"])
    assert result.command == "assets.list"
    assert result.details["status"] == "ok"
    assert result.details["operation_scope"] == "source_repo_asset_inventory_view"
    assert isinstance(result.details["asset_count"], int)
    assets = result.details["assets"]
    assert isinstance(assets, list)
    assert assets
    first = assets[0]
    assert "asset_id" in first
    assert "runtime_adapter" in first


def test_run_cli_supports_assets_discover_command() -> None:
    result = run_cli(["assets", "discover"])
    assert result.command == "assets.discover"
    assert result.details["status"] == "ok"
    assert result.details["operation_scope"] == "source_repo_asset_inventory_view"
    assert result.details["asset_count"] == len(result.details["assets"])


def test_run_cli_supports_assets_install_command(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    source_dir = repo_root / "source" / "asset.demo"
    source_dir.mkdir(parents=True)
    (source_dir / "entry.py").write_text("print('demo')\n", encoding="utf-8")
    (source_dir / "manifest.json").write_text(
        """
{
  "asset_id": "asset.demo",
  "asset_type": "skill",
  "name": "asset_demo",
  "version": "1.0.0",
  "entry": "entry.py",
  "owner": "test",
  "owner_role": "qa",
  "dependencies": [],
  "source_path": "source/asset.demo",
  "description": "demo asset",
  "metadata": {}
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    runtime_home = tmp_path / "agentsystem-home"
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("app.cli._repo_root", lambda: repo_root)

    result = run_cli(["assets", "install", "asset.demo"])

    assert result.command == "assets.install"
    assert result.details["status"] == "ok"
    assert result.details["operation_scope"] == "single_asset_install_flow"
    assert result.details["asset_id"] == "asset.demo"
    installed_manifest = Path(str(result.details["installed_manifest"]))
    assert installed_manifest.exists()
    installed_data = installed_manifest.read_text(encoding="utf-8")
    assert '"asset_id": "asset.demo"' in installed_data
    assert Path(str(result.details["build_output_path"])).exists()
    assert Path(str(result.details["installed_path"])).exists()


def test_run_cli_assets_install_reports_missing_asset(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "source").mkdir(parents=True)
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(tmp_path / "agentsystem-home"))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("app.cli._repo_root", lambda: repo_root)

    result = run_cli(["assets", "install", "asset.missing"])

    assert result.command == "assets.install"
    assert result.exit_code == 1
    assert result.details["status"] == "error"
    assert result.details["error"] == "asset_not_found"
    assert result.details["asset_id"] == "asset.missing"
