#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG=/tmp/e2e_full_run.log
PID=/tmp/e2e_full_run.pid
STATUS=/tmp/e2e_full_run.status
: > "$LOG"
echo "starting $(date -Is)" > "$STATUS"
export PYTHONUNBUFFERED=1
exec "$ROOT/.venv/bin/python3" "$ROOT/tests/e2e/test_50_scenarios_20_turns_user_level.py" \
  --base-url http://localhost:80 \
  --delay 5 \
  --timeout 180 \
  >> "$LOG" 2>&1
