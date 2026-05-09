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

pkill -f "uvicorn app.system.http_test_server:app" 2>/dev/null || true
pkill -f "python3 -m uvicorn app.system.http_test_server:app" 2>/dev/null || true
pkill -f ".venv/bin/python3 -m uvicorn app.system.http_test_server:app" 2>/dev/null || true

for _ in $(seq 1 30); do
  if ! ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    break
  fi
  sleep 1
done

WORKERS="${WORKERS:-1}"

if [ -x "$PROJECT_DIR/.venv/bin/python3" ]; then
  nohup "$PROJECT_DIR/.venv/bin/python3" -m uvicorn app.system.http_test_server:app --host 0.0.0.0 --port "$PORT" --workers "$WORKERS" --timeout-keep-alive 120 >> "$LOG_PATH" 2>&1 &
else
  nohup python3 -m uvicorn app.system.http_test_server:app --host 0.0.0.0 --port "$PORT" --workers "$WORKERS" --timeout-keep-alive 120 >> "$LOG_PATH" 2>&1 &
fi

SERVER_PID=$!
printf '=== phase3-subset-server-pid %s ===\n' "$SERVER_PID" >> "$LOG_PATH"
echo "$SERVER_PID"
