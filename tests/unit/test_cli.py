from __future__ import annotations

from pathlib import Path

from app.cli import build_parser, run_cli
from app.runtime_paths import resolve_runtime_paths

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_demo_asset(repo_root: Path, asset_id: str) -> None:
    asset_dir = repo_root / "source" / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "entry.py").write_text(f"print('{asset_id}')\n", encoding="utf-8")
    (asset_dir / "manifest.json").write_text(
        f"""
{{
  "asset_id": "{asset_id}",
  "asset_type": "skill",
  "name": "{asset_id.replace('.', '_')}",
  "version": "1.0.0",
  "entry": "entry.py",
  "owner": "test",
  "owner_role": "qa",
  "dependencies": [],
  "source_path": "source/{asset_id}",
  "description": "demo asset {asset_id}",
  "metadata": {{}}
}}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_build_parser_supports_phase1_command_surface() -> None:
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    for name in [
        "start",
        "stop",
        "restart",
        "status",
        "install",
        "bootstrap",
        "doctor",
        "runtime-layout",
        "migrate-runtime",
        "assets",
        "serve",
    ]:
        assert name in choices


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


def test_run_cli_start_suggested_command_uses_package_native_serve() -> None:
    result = run_cli(["doctor"])
    suggested = str(result.details["suggested_start_command"])
    assert "AGENTSYSTEM_DATA_DIR=" in suggested
    assert "-m app.cli serve" in suggested
    assert "--app-dir" not in suggested


def test_run_cli_start_uses_installed_runtime_lifecycle_control(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_home = tmp_path / "agentsystem-home"
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("app.cli._repo_root", lambda: repo_root)

    class FakePopen:
        def __init__(self, command, cwd, env, stdout, stderr, start_new_session):
            self.pid = 43210

    monkeypatch.setattr("app.cli.subprocess.Popen", FakePopen)

    result = run_cli(["start"])

    assert result.command == "start"
    assert result.details["status"] == "ok"
    assert result.details["operation_scope"] == "installed_runtime_lifecycle_control"
    assert result.details["pid"] == 43210
    assert Path(str(result.details["pid_file"])).read_text(encoding="utf-8").strip() == "43210"
    assert result.details["launch_command"][-4:] == ["--host", "0.0.0.0", "--port", "80"]


def test_run_cli_stop_clears_running_pid_file(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_home = tmp_path / "agentsystem-home"
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("app.cli._repo_root", lambda: repo_root)

    class FakePopen:
        def __init__(self, command, cwd, env, stdout, stderr, start_new_session):
            self.pid = 54321

    running = {54321}

    def fake_kill(target_pid: int, sig: int) -> None:
        if sig == 0 and target_pid in running:
            return
        if sig != 0 and target_pid in running:
            running.remove(target_pid)
            return
        raise OSError("not running")

    monkeypatch.setattr("app.cli.subprocess.Popen", FakePopen)
    monkeypatch.setattr("app.cli.os.kill", fake_kill)

    start = run_cli(["start"])
    pid_file = Path(str(start.details["pid_file"]))
    stop = run_cli(["stop"])

    assert stop.command == "stop"
    assert stop.details["status"] == "ok"
    assert stop.details["stopped"] is True
    assert not pid_file.exists()


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


def test_run_cli_returns_doctor_checks() -> None:
    result = run_cli(["doctor"])
    assert result.command == "doctor"
    assert result.details["status"] in {"ok", "needs_attention"}
    assert result.details["operation_scope"] == "resolved_runtime_health_view"
    assert isinstance(result.details["checks"], dict)
    assert "config_dir" in result.details["checks"]
    assert "service_process" in result.details


def test_run_cli_bootstrap_seeds_legacy_config_and_installs_assets(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_demo_asset(repo_root, "asset.bootstrap.demo")
    runtime_home = tmp_path / "agentsystem-home"
    legacy_home = tmp_path / "legacy-home"
    legacy_config = legacy_home / ".config" / "agentsystem" / "config.yaml"
    legacy_config.parent.mkdir(parents=True, exist_ok=True)
    legacy_config.write_text("models: {}\n", encoding="utf-8")
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: legacy_home)
    monkeypatch.setattr("app.cli._repo_root", lambda: repo_root)

    first = run_cli(["bootstrap"])
    second = run_cli(["bootstrap"])

    assert first.command == "bootstrap"
    assert first.details["status"] == "ok"
    assert first.details["config_status"] == "seeded_from_legacy"
    assert first.details["installed_asset_count"] == 1
    assert second.details["runtime_registry_created"] is False


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
    assert result.details["migration_status"] == "attention_needed"
    assert result.details["warnings"]


def test_repo_shell_wrappers_delegate_to_python_cli() -> None:
    start_wrapper = (REPO_ROOT / "start_server.sh").read_text(encoding="utf-8")
    stop_wrapper = (REPO_ROOT / "stop_server.sh").read_text(encoding="utf-8")
    start_web_wrapper = (REPO_ROOT / "start_web_server.sh").read_text(encoding="utf-8")
    assert 'app/cli.py" start' in start_wrapper
    assert 'app/cli.py" stop' in stop_wrapper
    assert 'app/cli.py" start' in start_web_wrapper


def test_run_cli_status_reports_bootstrap_gaps(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_home = tmp_path / "agentsystem-home"
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("app.cli._repo_root", lambda: repo_root)

    result = run_cli(["status"])

    assert result.details["status"] == "needs_attention"
    assert result.details["checks"]["runtime_registry_ready"] is False
    assert result.details["checks"]["builtin_paths_ready"] is False
    assert result.details["checks"]["installed_assets_present"] is False


def test_run_cli_doctor_reports_bootstrapped_runtime_assets(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_demo_asset(repo_root, "asset.doctor.demo")
    runtime_home = tmp_path / "agentsystem-home"
    (runtime_home / "config").mkdir(parents=True)
    (runtime_home / "config" / "config.yaml").write_text("models: {}\n", encoding="utf-8")
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("app.cli._repo_root", lambda: repo_root)

    run_cli(["bootstrap"])
    result = run_cli(["doctor"])

    assert result.details["required_core_assets"]["runtime_registry"] is True
    assert result.details["required_core_assets"]["builtin_paths"] is True
    assert "asset.doctor.demo" in result.details["installed_asset_ids"]


def test_install_lifecycle_supports_clean_bootstrap_incremental_install_and_idempotent_reinstall(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_demo_asset(repo_root, "asset.alpha")
    runtime_home = tmp_path / "agentsystem-home"
    (runtime_home / "config").mkdir(parents=True)
    (runtime_home / "config" / "config.yaml").write_text("models: {}\n", encoding="utf-8")
    monkeypatch.setenv("AGENTSYSTEM_HOME", str(runtime_home))
    monkeypatch.delenv("AGENTSYSTEM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("app.cli._repo_root", lambda: repo_root)

    bootstrap_result = run_cli(["bootstrap"])
    status_after_bootstrap = run_cli(["status"])
    doctor_after_bootstrap = run_cli(["doctor"])

    assert bootstrap_result.details["installed_asset_count"] == 1
    assert status_after_bootstrap.details["checks"]["runtime_registry_ready"] is True
    assert "asset.alpha" in doctor_after_bootstrap.details["installed_asset_ids"]

    _write_demo_asset(repo_root, "asset.beta")
    incremental_install = run_cli(["assets", "install", "asset.beta"])
    install_all_first = run_cli(["assets", "install-all"])
    install_all_second = run_cli(["assets", "install-all"])
    final_doctor = run_cli(["doctor"])

    assert incremental_install.details["asset_id"] == "asset.beta"
    assert install_all_first.details["installed_asset_count"] == 2
    assert install_all_second.details["installed_asset_count"] == 2
    assert {row["asset_id"] for row in install_all_second.details["results"]} == {"asset.alpha", "asset.beta"}
    assert {"builtin_paths", "asset.alpha", "asset.beta"}.issubset(set(final_doctor.details["installed_asset_ids"]))


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
