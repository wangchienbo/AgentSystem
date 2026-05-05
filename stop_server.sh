#!/bin/bash
# Compatibility wrapper for the Python AgentSystem CLI.

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$PROJECT_DIR:${PYTHONPATH:-}"

if [ -f "$PROJECT_DIR/.venv/bin/python3" ]; then
  exec "$PROJECT_DIR/.venv/bin/python3" -m app.cli stop "$@"
fi

exec python3 -m app.cli stop "$@"
