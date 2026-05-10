from __future__ import annotations

from pathlib import Path

from app.cli import build_parser, run_cli

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
    assert result.command == "status"
    assert result.details["status"] in {"ok", "needs_attention"}
    assert str(result.details["repo_root"]) == str(REPO_ROOT)
    assert "service_reachable" in result.details
    assert "config_file" in result.details


def test_run_cli_returns_not_implemented_contract_for_start() -> None:
    result = run_cli(["start"])
    assert result.command == "start"
    assert result.exit_code == 2
    assert result.details["status"] == "not_implemented"
    assert "next_step" in result.details
    assert "--app-dir" in str(result.details["suggested_start_command"])
    assert "AGENTSYSTEM_DATA_DIR=" in str(result.details["suggested_start_command"])
    assert "-m uvicorn app.system.http_test_server:app" in str(result.details["suggested_start_command"])


def test_run_cli_returns_runtime_layout_contract() -> None:
    result = run_cli(["runtime-layout"])
    assert result.command == "runtime-layout"
    assert result.details["status"] == "ok"
    assert str(result.details["config_dir"]) == str(REPO_ROOT / "config")
    assert str(result.details["installed_dir"]) == str(REPO_ROOT / "installed")


def test_run_cli_returns_doctor_checks() -> None:
    result = run_cli(["doctor"])
    assert result.command == "doctor"
    assert result.details["status"] in {"ok", "needs_attention"}
    checks = result.details["checks"]
    assert isinstance(checks, dict)
    assert "config_dir" in checks
    assert "data_dir" in checks
    assert "config_file" in checks
    assert "service_reachable" in checks
    assert "suggested_start_command" in result.details


def test_repo_shell_wrappers_delegate_to_python_cli() -> None:
    start_wrapper = (REPO_ROOT / "start_server.sh").read_text(encoding="utf-8")
    stop_wrapper = (REPO_ROOT / "stop_server.sh").read_text(encoding="utf-8")
    start_web_wrapper = (REPO_ROOT / "start_web_server.sh").read_text(encoding="utf-8")
    assert "-m app.cli start" in start_wrapper
    assert "-m app.cli stop" in stop_wrapper
    assert "-m app.cli start" in start_web_wrapper


def test_run_cli_supports_assets_install_command() -> None:
    result = run_cli(["assets", "install", "asset.demo"])
    assert result.command == "assets.install"
    assert result.details["status"] == "planned"
    assert result.details["asset_id"] == "asset.demo"
