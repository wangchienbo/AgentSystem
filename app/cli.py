from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.error import URLError
from urllib.request import urlopen

from app.bootstrap.runtime import describe_phase6_asset_bootstrap_binding, materialize_builtin_path_definitions
from app.runtime_paths import resolve_runtime_paths
from app.skills.system_skill_registry import SYSTEM_SKILL_SPECS
from app.system.catalog.asset_center import AssetCenter


@dataclass(frozen=True)
class CLIResult:
    command: str
    details: dict[str, object]
    exit_code: int = 0


def _planned_command_result(command: str, repo_root: Path) -> CLIResult:
    runtime_paths = resolve_runtime_paths(repo_root)
    return CLIResult(
        command=command,
        exit_code=2,
        details={
            "status": "not_implemented",
            "repo_root": str(repo_root),
            "operation_scope": "installed_runtime_target_not_yet_wired",
            "next_step": "use status/doctor to inspect readiness before wiring live runtime control",
            "suggested_start_command": _start_command(repo_root),
            "home_dir": str(runtime_paths.home_dir),
        },
    )


def _install_all_assets(repo_root: Path) -> dict[str, object]:
    runtime_paths = resolve_runtime_paths(repo_root)
    asset_center = AssetCenter(
        source_dir=str(repo_root / "source"),
        installed_dir=str(runtime_paths.installed_assets_dir),
        build_dir=str(runtime_paths.build_dir),
        data_dir=str(runtime_paths.data_dir),
    )
    discovered = asset_center.discover()
    installed_results: list[dict[str, object]] = []
    for asset in discovered:
        build_record = asset_center.build(asset.asset_id)
        installed_version = asset_center.install(asset.asset_id, build_record.build_hash)
        installed_results.append(
            {
                "asset_id": asset.asset_id,
                "asset_name": asset.name,
                "asset_type": asset.asset_type,
                "installed_version": installed_version,
                "build_hash": build_record.build_hash,
                "build_output_path": str(runtime_paths.build_dir / asset.asset_id / build_record.build_hash),
                "installed_path": str(runtime_paths.installed_assets_dir / asset.asset_id),
            }
        )
    return {
        "runtime_paths": runtime_paths,
        "discovered": discovered,
        "results": installed_results,
    }


def _bootstrap_runtime_layout(repo_root: Path) -> CLIResult:
    runtime_paths = resolve_runtime_paths(repo_root)
    created_dirs: list[str] = []
    existing_dirs: list[str] = []
    for path in [
        runtime_paths.home_dir,
        runtime_paths.config_dir,
        runtime_paths.data_dir,
        runtime_paths.state_dir,
        runtime_paths.cache_dir,
        runtime_paths.logs_dir,
        runtime_paths.installed_assets_dir,
        runtime_paths.build_dir,
    ]:
        if path.exists():
            existing_dirs.append(str(path))
        else:
            path.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(path))

    copied_files: list[str] = []
    config_status = "existing"
    legacy_config = Path.home() / ".config" / "agentsystem" / "config.yaml"
    if not runtime_paths.config_file.exists() and legacy_config.exists():
        runtime_paths.config_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_config, runtime_paths.config_file)
        copied_files.append(str(runtime_paths.config_file))
        config_status = "seeded_from_legacy"
    elif runtime_paths.config_file.exists():
        config_status = "existing"
    else:
        config_status = "missing"

    repo_overlap = {
        name: str(path)
        for name, path in {
            "config_dir": runtime_paths.config_dir,
            "data_dir": runtime_paths.data_dir,
            "state_dir": runtime_paths.state_dir,
            "cache_dir": runtime_paths.cache_dir,
            "logs_dir": runtime_paths.logs_dir,
            "installed_assets_dir": runtime_paths.installed_assets_dir,
            "build_dir": runtime_paths.build_dir,
        }.items()
        if repo_root == path or repo_root in path.parents
    }

    next_actions: list[str] = []
    if config_status == "missing":
        next_actions.append(f"create config file at {runtime_paths.config_file}")
    if repo_overlap:
        next_actions.append("move AGENTSYSTEM_* runtime roots outside repo before running installed-runtime migration")

    builtin_paths_dir = materialize_builtin_path_definitions(repo_root)
    install_summary = _install_all_assets(repo_root)
    runtime_registry_file = runtime_paths.state_dir / "runtime_center.json"
    runtime_registry_created = False
    if not runtime_registry_file.exists():
        runtime_registry_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_registry_file.write_text('{\n  "entries": {},\n  "sessions": {}\n}\n', encoding="utf-8")
        runtime_registry_created = True

    return CLIResult(
        command="bootstrap",
        details={
            "status": "ok",
            "operation_scope": "runtime_layout_initialization",
            "repo_root": str(repo_root),
            "home_dir": str(runtime_paths.home_dir),
            "config_file": str(runtime_paths.config_file),
            "created_dirs": created_dirs,
            "existing_dirs": existing_dirs,
            "copied_files": copied_files,
            "config_status": config_status,
            "legacy_config_checked": str(legacy_config),
            "repo_overlap": repo_overlap,
            "builtin_paths_dir": str(builtin_paths_dir),
            "runtime_registry_file": str(runtime_registry_file),
            "runtime_registry_created": runtime_registry_created,
            "installed_asset_count": len(install_summary["results"]),
            "installed_assets": install_summary["results"],
            "next_actions": next_actions,
        },
    )


def _migrate_runtime(repo_root: Path) -> CLIResult:
    runtime_paths = resolve_runtime_paths(repo_root)
    legacy_candidates = {
        "legacy_repo_installed_dir": runtime_paths.legacy_repo_installed_dir,
        "legacy_repo_build_dir": runtime_paths.legacy_repo_build_dir,
        "legacy_repo_runtime_center": repo_root / "data" / "runtime_center.json",
        "legacy_repo_chat_logs": repo_root / "data" / "chat_logs",
        "legacy_repo_skill_assets": repo_root / "data" / "skill_assets",
    }
    found_legacy = {name: str(path) for name, path in legacy_candidates.items() if path.exists()}
    repo_overlap = {
        name: str(path)
        for name, path in {
            "config_dir": runtime_paths.config_dir,
            "data_dir": runtime_paths.data_dir,
            "state_dir": runtime_paths.state_dir,
            "cache_dir": runtime_paths.cache_dir,
            "logs_dir": runtime_paths.logs_dir,
            "installed_assets_dir": runtime_paths.installed_assets_dir,
            "build_dir": runtime_paths.build_dir,
        }.items()
        if repo_root == path or repo_root in path.parents
    }

    warnings: list[str] = []
    if found_legacy:
        warnings.append("legacy repo-local runtime artifacts still exist")
    if repo_overlap:
        warnings.append("runtime path environment still points inside repo")

    next_actions: list[str] = []
    if found_legacy:
        next_actions.append("review legacy repo-local runtime artifacts before deleting or copying them")
    if repo_overlap:
        next_actions.append("reconfigure AGENTSYSTEM_* runtime roots to locations outside repo")
    if not next_actions:
        next_actions.append("runtime layout looks ready for deeper migrate-runtime wiring")

    return CLIResult(
        command="migrate-runtime",
        details={
            "status": "ok",
            "operation_scope": "runtime_migration_audit",
            "repo_root": str(repo_root),
            "home_dir": str(runtime_paths.home_dir),
            "found_legacy_paths": found_legacy,
            "repo_overlap": repo_overlap,
            "warnings": warnings,
            "next_actions": next_actions,
            "migration_status": "attention_needed" if (found_legacy or repo_overlap) else "ready_for_wiring",
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentsystem", description="AgentSystem operator CLI")
    subparsers = parser.add_subparsers(dest="command")

    for name in ["start", "stop", "restart", "status", "install", "bootstrap", "doctor", "runtime-layout", "migrate-runtime", "serve"]:
        subparsers.add_parser(name)

    serve = subparsers.choices["serve"]
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=80)

    assets = subparsers.add_parser("assets")
    assets_subparsers = assets.add_subparsers(dest="assets_command")
    assets_subparsers.add_parser("list")
    assets_subparsers.add_parser("discover")
    install_parser = assets_subparsers.add_parser("install")
    install_parser.add_argument("asset_id")
    assets_subparsers.add_parser("install-all")

    return parser


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _builtin_asset_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for skill_id, spec in sorted(SYSTEM_SKILL_SPECS.items()):
        manifest = spec["manifest"]
        records.append(
            {
                "asset_id": skill_id,
                "name": spec["name"],
                "origin": "builtin",
                "runtime_adapter": manifest.runtime_adapter,
                "version": spec["version"],
            }
        )
    return records


    records: list[dict[str, object]] = []
    for skill_id, spec in sorted(SYSTEM_SKILL_SPECS.items()):
        manifest = spec["manifest"]
        records.append(
            {
                "asset_id": skill_id,
                "name": spec["name"],
                "origin": "builtin",
                "runtime_adapter": manifest.runtime_adapter,
                "version": spec["version"],
            }
        )
    return records


def _runtime_layout(repo_root: Path) -> dict[str, object]:
    runtime_paths = resolve_runtime_paths(repo_root)
    return {
        "repo_root": str(repo_root),
        "layout_mode": "transition_install_model_ready",
        "operation_scope": "resolved_runtime_layout_view",
        **runtime_paths.as_dict(),
        "asset_root_transition": {
            "installed_runtime_assets": str(runtime_paths.installed_assets_dir),
            "build_artifacts": str(runtime_paths.build_dir),
            "legacy_repo_installed": str(runtime_paths.legacy_repo_installed_dir),
            "legacy_repo_build": str(runtime_paths.legacy_repo_build_dir),
            "bootstrap_status": "install_model_asset_roots_live_repo_source_retained",
        },
        "bootstrap_asset_binding": describe_phase6_asset_bootstrap_binding(
            repo_root,
            installed_assets_mode="install-model-preview",
        ),
        "bootstrap_asset_binding_preview": describe_phase6_asset_bootstrap_binding(repo_root),
    }


def _start_runtime(repo_root: Path, port: int = 80, host: str = "0.0.0.0") -> CLIResult:
    runtime_paths = resolve_runtime_paths(repo_root)
    runtime_paths.state_dir.mkdir(parents=True, exist_ok=True)
    runtime_paths.logs_dir.mkdir(parents=True, exist_ok=True)
    state = _service_process_state(repo_root)
    if state["running"]:
        return CLIResult(
            command="start",
            details={
                "status": "already_running",
                "operation_scope": "installed_runtime_lifecycle_control",
                **state,
            },
        )
    pid_file = Path(str(state["pid_file"]))
    if state["stale_pid_file"]:
        pid_file.unlink(missing_ok=True)
    log_file = runtime_paths.logs_dir / "http_test_server.log"
    env = os.environ.copy()
    env.setdefault("AGENTSYSTEM_DATA_DIR", str(runtime_paths.data_dir))
    command = [sys.executable, "-m", "app.cli", "serve", "--host", host, "--port", str(port)]
    with log_file.open("ab") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    return CLIResult(
        command="start",
        details={
            "status": "ok",
            "operation_scope": "installed_runtime_lifecycle_control",
            "pid": process.pid,
            "pid_file": str(pid_file),
            "log_file": str(log_file),
            "launch_command": command,
            "host": host,
            "port": port,
        },
    )


def _stop_runtime(repo_root: Path) -> CLIResult:
    state = _service_process_state(repo_root)
    pid_file = Path(str(state["pid_file"]))
    pid = state["pid"]
    if not pid or not state["running"]:
        if state["stale_pid_file"]:
            pid_file.unlink(missing_ok=True)
        return CLIResult(
            command="stop",
            details={
                "status": "not_running",
                "operation_scope": "installed_runtime_lifecycle_control",
                **state,
            },
        )
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not _pid_running(pid):
            break
        time.sleep(0.1)
    stopped = not _pid_running(pid)
    if stopped:
        pid_file.unlink(missing_ok=True)
    return CLIResult(
        command="stop",
        exit_code=0 if stopped else 1,
        details={
            "status": "ok" if stopped else "timeout",
            "operation_scope": "installed_runtime_lifecycle_control",
            "pid": pid,
            "pid_file": str(pid_file),
            "stopped": stopped,
        },
    )


def _restart_runtime(repo_root: Path) -> CLIResult:
    stop_result = _stop_runtime(repo_root)
    start_result = _start_runtime(repo_root)
    return CLIResult(
        command="restart",
        exit_code=max(stop_result.exit_code, start_result.exit_code),
        details={
            "status": "ok" if start_result.details["status"] in {"ok", "already_running"} else "error",
            "operation_scope": "installed_runtime_lifecycle_control",
            "stop": stop_result.details,
            "start": start_result.details,
        },
    )


def _service_health(port: int = 80) -> dict[str, object]:
    url = f"http://localhost:{port}/api/status"
    try:
        with urlopen(url, timeout=2.0) as response:
            return {
                "service_reachable": True,
                "service_status_code": getattr(response, "status", 200),
                "service_url": url,
            }
    except URLError as exc:
        return {
            "service_reachable": False,
            "service_error": str(exc.reason or exc),
            "service_url": url,
        }
    except Exception as exc:
        return {
            "service_reachable": False,
            "service_error": f"{type(exc).__name__}: {exc}",
            "service_url": url,
        }


def _pid_file(repo_root: Path) -> Path:
    runtime_paths = resolve_runtime_paths(repo_root)
    return runtime_paths.state_dir / "http_test_server.pid"


def _read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _service_process_state(repo_root: Path) -> dict[str, object]:
    pid_file = _pid_file(repo_root)
    pid = _read_pid(pid_file)
    running = bool(pid and _pid_running(pid))
    stale_pid_file = bool(pid_file.exists() and not running)
    return {
        "pid_file": str(pid_file),
        "pid": pid,
        "running": running,
        "stale_pid_file": stale_pid_file,
    }
def _installed_service_command(port: int = 80) -> list[str]:
    return [sys.executable, "-m", "app.cli", "serve", "--host", "0.0.0.0", "--port", str(port)]


def _shell_join(parts: Sequence[str]) -> str:
    return " ".join(str(part) for part in parts)


def _start_command(repo_root: Path, port: int = 80) -> str:
    runtime_paths = resolve_runtime_paths(repo_root)
    runtime_dir = runtime_paths.data_dir
    command = _installed_service_command(port)
    return f"mkdir -p {runtime_dir} && AGENTSYSTEM_DATA_DIR={runtime_dir} {_shell_join(command)}"


def _serve_command(host: str, port: int) -> CLIResult:
    import uvicorn

    uvicorn.run("app.system.http_test_server:app", host=host, port=port)
    return CLIResult(
        command="serve",
        details={
            "status": "stopped",
            "operation_scope": "installed_runtime_service_entrypoint",
            "host": host,
            "port": port,
        },
    )




def _doctor_status(repo_root: Path) -> dict[str, object]:
    layout = _runtime_layout(repo_root)
    runtime_paths = resolve_runtime_paths(repo_root)
    runtime_registry_file = runtime_paths.state_dir / "runtime_center.json"
    builtin_paths_manifest = runtime_paths.installed_assets_dir / "builtin_paths" / "builtin_paths_manifest.json"
    installed_asset_dirs = sorted(path for path in runtime_paths.installed_assets_dir.iterdir() if path.is_dir()) if runtime_paths.installed_assets_dir.exists() else []
    required_core_assets = {
        "builtin_paths": builtin_paths_manifest.exists(),
        "runtime_registry": runtime_registry_file.exists(),
    }
    checks = {
        key: Path(str(value)).exists()
        for key, value in layout.items()
        if key
        not in {
            "repo_root",
            "layout_mode",
            "operation_scope",
            "legacy_repo_installed_dir",
            "legacy_repo_build_dir",
            "asset_root_transition",
            "bootstrap_asset_binding",
            "bootstrap_asset_binding_preview",
        }
    }
    service = _service_health()
    checks["service_reachable"] = bool(service["service_reachable"])
    checks["runtime_registry_ready"] = required_core_assets["runtime_registry"]
    checks["builtin_paths_ready"] = required_core_assets["builtin_paths"]
    checks["installed_assets_present"] = bool(installed_asset_dirs)
    missing_checks = [name for name, ok in checks.items() if not ok]
    status = "ok" if not missing_checks else "needs_attention"
    next_actions: list[str] = []
    if not checks["config_file"]:
        next_actions.append(f"create config file at {layout['config_file']}")
    if not checks["runtime_registry_ready"] or not checks["builtin_paths_ready"] or not checks["installed_assets_present"]:
        next_actions.append("run agentsystem bootstrap to initialize install-model runtime assets and metadata")
    if not checks["service_reachable"]:
        next_actions.append(f"start local HTTP service via: {_start_command(repo_root)}")
    for key in [
        "home_dir",
        "config_dir",
        "data_dir",
        "state_dir",
        "cache_dir",
        "logs_dir",
        "installed_assets_dir",
        "build_dir",
    ]:
        if not checks.get(key):
            next_actions.append(f"create runtime directory: {layout[key]}")
    process_state = _service_process_state(repo_root)
    return {
        "status": status,
        "status_reason": "all_transition_checks_passed" if status == "ok" else "missing_transition_prerequisites",
        "missing_checks": missing_checks,
        "checks": checks,
        "required_core_assets": required_core_assets,
        "installed_asset_count": len(installed_asset_dirs),
        "installed_asset_ids": [path.name for path in installed_asset_dirs],
        "runtime_registry_file": str(runtime_registry_file),
        "builtin_paths_manifest": str(builtin_paths_manifest),
        "suggested_start_command": _start_command(repo_root),
        "service_process": process_state,
        "next_actions": next_actions,
        **service,
        **layout,
        "operation_scope": "resolved_runtime_health_view",
    }


def run_cli(argv: Sequence[str] | None = None) -> CLIResult:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return CLIResult(command="help", details={"message": "help displayed"})

    repo_root = _repo_root()
    if args.command == "start":
        return _start_runtime(repo_root)
    if args.command == "stop":
        return _stop_runtime(repo_root)
    if args.command == "restart":
        return _restart_runtime(repo_root)
    if args.command == "status":
        return CLIResult(command="status", details=_doctor_status(repo_root))
    if args.command == "doctor":
        return CLIResult(command="doctor", details=_doctor_status(repo_root))
    if args.command == "runtime-layout":
        return CLIResult(command="runtime-layout", details={"status": "ok", **_runtime_layout(repo_root)})
    if args.command == "migrate-runtime":
        return _migrate_runtime(repo_root)
    if args.command == "bootstrap":
        return _bootstrap_runtime_layout(repo_root)
    if args.command == "serve":
        return _serve_command(host=args.host, port=args.port)

    if args.command == "assets":
        asset_command = getattr(args, "assets_command", None)
        if asset_command in {"list", "discover"}:
            assets = _builtin_asset_records()
            return CLIResult(
                command=f"assets.{asset_command}",
                details={
                    "status": "ok",
                    "operation_scope": "source_repo_asset_inventory_view",
                    "asset_count": len(assets),
                    "assets": assets,
                    "repo_root": str(repo_root),
                },
            )
        if asset_command == "install":
            runtime_paths = resolve_runtime_paths(repo_root)
            asset_center = AssetCenter(
                source_dir=str(repo_root / "source"),
                installed_dir=str(runtime_paths.installed_assets_dir),
                build_dir=str(runtime_paths.build_dir),
                data_dir=str(runtime_paths.data_dir),
            )
            discovered = asset_center.discover()
            asset = asset_center.get_asset(args.asset_id)
            if asset is None:
                return CLIResult(
                    command="assets.install",
                    exit_code=1,
                    details={
                        "status": "error",
                        "error": "asset_not_found",
                        "asset_id": args.asset_id,
                        "discovered_asset_count": len(discovered),
                        "repo_root": str(repo_root),
                    },
                )
            build_record = asset_center.build(args.asset_id)
            installed_version = asset_center.install(args.asset_id, build_record.build_hash)
            installed_manifest = runtime_paths.installed_assets_dir / args.asset_id / "installed.json"
            return CLIResult(
                command="assets.install",
                details={
                    "status": "ok",
                    "operation_scope": "single_asset_install_flow",
                    "asset_id": args.asset_id,
                    "asset_name": asset.name,
                    "asset_type": asset.asset_type,
                    "installed_version": installed_version,
                    "build_hash": build_record.build_hash,
                    "source_dir": str(repo_root / "source"),
                    "installed_path": str(runtime_paths.installed_assets_dir / args.asset_id),
                    "build_output_path": str(runtime_paths.build_dir / args.asset_id / build_record.build_hash),
                    "installed_manifest": str(installed_manifest),
                    "repo_root": str(repo_root),
                },
            )
        if asset_command == "install-all":
            install_summary = _install_all_assets(repo_root)
            discovered = install_summary["discovered"]
            installed_results = install_summary["results"]
            return CLIResult(
                command="assets.install-all",
                details={
                    "status": "ok",
                    "operation_scope": "bulk_asset_install_flow",
                    "repo_root": str(repo_root),
                    "source_dir": str(repo_root / "source"),
                    "discovered_asset_count": len(discovered),
                    "installed_asset_count": len(installed_results),
                    "results": installed_results,
                },
            )

    if args.command == "runtime-layout":
        return CLIResult(
            command="runtime-layout",
            details={"status": "ok", **_runtime_layout(repo_root)},
        )

    if args.command in {"status", "doctor"}:
        return CLIResult(
            command=args.command,
            details=_doctor_status(repo_root),
        )

    if args.command == "bootstrap":
        return _bootstrap_runtime_layout(repo_root)

    if args.command == "migrate-runtime":
        return _migrate_runtime(repo_root)

    if args.command in {"start", "stop", "restart", "install"}:
        return _planned_command_result(args.command, repo_root)

    return CLIResult(
        command=args.command,
        details={"status": "planned", "repo_root": str(repo_root)},
    )


def main(argv: Sequence[str] | None = None) -> int:
    result = run_cli(argv)
    print(f"command={result.command}")
    for key, value in result.details.items():
        print(f"{key}={value}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
