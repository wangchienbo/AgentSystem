#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_PATH="${1:-/tmp/agentsystem_phase3_subset.log}"
PORT="${PORT:-80}"
MARKER="phase3-subset-start $(date -Iseconds) pid=$$"

cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR:${PYTHONPATH:-}"

: > "$LOG_PATH"
printf '=== %s ===\n' "$MARKER" >> "$LOG_PATH"

pkill -f "$PROJECT_DIR/.venv/bin/python3 -m uvicorn app.system.http_test_server:app" 2>/dev/null || true

if [ -x "$PROJECT_DIR/.venv/bin/python3" ]; then
  nohup "$PROJECT_DIR/.venv/bin/python3" -m uvicorn app.system.http_test_server:app --host 0.0.0.0 --port "$PORT" >> "$LOG_PATH" 2>&1 &
else
  nohup python3 -m uvicorn app.system.http_test_server:app --host 0.0.0.0 --port "$PORT" >> "$LOG_PATH" 2>&1 &
fi

SERVER_PID=$!
printf '=== phase3-subset-server-pid %s ===\n' "$SERVER_PID" >> "$LOG_PATH"
echo "$SERVER_PID"
