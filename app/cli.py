from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.error import URLError
from urllib.request import urlopen

from app.bootstrap.runtime import describe_phase6_asset_bootstrap_binding
from app.runtime_paths import resolve_runtime_paths
from app.skills.system_skill_registry import SYSTEM_SKILL_SPECS


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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentsystem", description="AgentSystem operator CLI")
    subparsers = parser.add_subparsers(dest="command")

    for name in ["start", "stop", "restart", "status", "install", "bootstrap", "doctor", "runtime-layout", "migrate-runtime"]:
        subparsers.add_parser(name)

    assets = subparsers.add_parser("assets")
    assets_subparsers = assets.add_subparsers(dest="assets_command")
    assets_subparsers.add_parser("list")
    assets_subparsers.add_parser("discover")
    install_parser = assets_subparsers.add_parser("install")
    install_parser.add_argument("asset_id")
    assets_subparsers.add_parser("install-all")

    return parser


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
            "bootstrap_status": "repo_pinned_during_transition",
        },
        "bootstrap_asset_binding": describe_phase6_asset_bootstrap_binding(repo_root),
        "bootstrap_asset_binding_preview": describe_phase6_asset_bootstrap_binding(
            repo_root,
            installed_assets_mode="install-model-preview",
        ),
    }


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


def _start_command(repo_root: Path, port: int = 80) -> str:
    python_bin = repo_root / ".venv" / "bin" / "python3"
    app_dir = repo_root
    runtime_paths = resolve_runtime_paths(repo_root)
    runtime_dir = runtime_paths.data_dir
    base = str(python_bin) if python_bin.exists() else "python3"
    return (
        f"mkdir -p {runtime_dir} && "
        f"AGENTSYSTEM_DATA_DIR={runtime_dir} "
        f"{base} -m uvicorn app.system.http_test_server:app "
        f"--app-dir {app_dir} --host 0.0.0.0 --port {port}"
    )


def _doctor_status(repo_root: Path) -> dict[str, object]:
    layout = _runtime_layout(repo_root)
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
    missing_checks = [name for name, ok in checks.items() if not ok]
    status = "ok" if not missing_checks else "needs_attention"
    next_actions: list[str] = []
    if not checks["config_file"]:
        next_actions.append(f"create config file at {layout['config_file']}")
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
    return {
        "status": status,
        "status_reason": "all_transition_checks_passed" if status == "ok" else "missing_transition_prerequisites",
        "missing_checks": missing_checks,
        "checks": checks,
        "suggested_start_command": _start_command(repo_root),
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
            return CLIResult(
                command="assets.install",
                details={
                    "asset_id": args.asset_id,
                    "status": "planned",
                    "repo_root": str(repo_root),
                },
            )
        return CLIResult(
            command=f"assets.{asset_command}",
            details={"status": "planned", "repo_root": str(repo_root)},
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

    if args.command in {"start", "stop", "restart", "install", "bootstrap", "migrate-runtime"}:
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
