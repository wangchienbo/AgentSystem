#!/bin/bash
# Compatibility wrapper for the Python AgentSystem CLI.

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$PROJECT_DIR/.venv/bin/python3" ]; then
  exec "$PROJECT_DIR/.venv/bin/python3" "$PROJECT_DIR/app/cli.py" stop "$@"
fi

exec python3 "$PROJECT_DIR/app/cli.py" stop "$@"
