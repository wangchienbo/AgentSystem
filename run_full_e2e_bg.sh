#!/usr/bin/env bash
set -euo pipefail
cd /root/project/AgentSystem
export PYTHONPATH=/root/project/AgentSystem
export PYTHONUNBUFFERED=1
exec .venv/bin/python3 -m tests.e2e.test_50_scenarios_20_turns_user_level \
  --base-url http://localhost:80 \
  --delay 5 \
  --timeout 180 \
  > /tmp/e2e_full_run.log 2>&1
