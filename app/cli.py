from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_LAYOUT_DIRS = {
    "config_dir": "config",
    "data_dir": "data",
    "logs_dir": "logs",
    "installed_dir": "installed",
    "build_dir": "build",
}


@dataclass(frozen=True)
class CLIResult:
    command: str
    details: dict[str, object]
    exit_code: int = 0


def _planned_command_result(command: str, repo_root: Path) -> CLIResult:
    return CLIResult(
        command=command,
        exit_code=2,
        details={
            "status": "not_implemented",
            "repo_root": str(repo_root),
            "operation_scope": "installed_runtime_target_not_yet_wired",
            "next_step": "use status/doctor to inspect readiness before wiring live runtime control",
            "suggested_start_command": _start_command(repo_root),
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


def _runtime_layout(repo_root: Path) -> dict[str, object]:
    layout: dict[str, object] = {
        "repo_root": str(repo_root),
        "layout_mode": "transition_repo_anchored",
        "operation_scope": "source_repo_layout_view",
    }
    for key, rel in DEFAULT_LAYOUT_DIRS.items():
        layout[key] = str(repo_root / rel)
    return layout


def _config_file() -> Path:
    return Path.home() / ".config" / "agentsystem" / "config.yaml"


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
    runtime_dir = repo_root / DEFAULT_LAYOUT_DIRS["data_dir"]
    base = str(python_bin) if python_bin.exists() else "python3"
    return (
        f"mkdir -p {runtime_dir} && "
        f"AGENTSYSTEM_DATA_DIR={runtime_dir} "
        f"{base} -m uvicorn app.system.http_test_server:app "
        f"--app-dir {app_dir} --host 0.0.0.0 --port {port}"
    )


def _doctor_status(repo_root: Path) -> dict[str, object]:
    layout = _runtime_layout(repo_root)
    config_file = _config_file()
    checks = {
        key: Path(str(value)).exists()
        for key, value in layout.items()
        if key != "repo_root"
    }
    checks["config_file"] = config_file.exists()
    service = _service_health()
    checks["service_reachable"] = bool(service["service_reachable"])
    return {
        "status": "ok" if all(checks.values()) else "needs_attention",
        "checks": checks,
        "config_file": str(config_file),
        "suggested_start_command": _start_command(repo_root),
        **service,
        **layout,
        "operation_scope": "source_repo_health_view",
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
