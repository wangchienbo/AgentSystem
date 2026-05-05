from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


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
