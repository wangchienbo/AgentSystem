from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


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


def _doctor_status(repo_root: Path) -> dict[str, object]:
    layout = _runtime_layout(repo_root)
    checks = {
        key: Path(str(value)).exists()
        for key, value in layout.items()
        if key != "repo_root"
    }
    return {
        "status": "ok" if all(checks.values()) else "needs_attention",
        "checks": checks,
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
