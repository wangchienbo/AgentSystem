from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.error import URLError
from urllib.request import urlopen


RUNTIME_LAYOUT_KEYS = {
    "repo_root": "/root/project/AgentSystem",
    "config_dir": "/root/project/AgentSystem/config",
    "data_dir": "/root/project/AgentSystem/data",
    "logs_dir": "/root/project/AgentSystem/logs",
    "installed_dir": "/root/project/AgentSystem/installed",
    "build_dir": "/root/project/AgentSystem/build",
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
            "next_step": "use status/doctor to inspect readiness before wiring live runtime control",
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
    return {
        "repo_root": str(repo_root),
        "config_dir": str(repo_root / "config"),
        "data_dir": str(repo_root / "data"),
        "logs_dir": str(repo_root / "logs"),
        "installed_dir": str(repo_root / "installed"),
        "build_dir": str(repo_root / "build"),
    }


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
        **service,
        **layout,
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
