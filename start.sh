#!/bin/bash
set -e

cd "$(dirname "$0")"
source .venv/bin/activate

if [ -z "${OPENAI_API_KEY:-}" ]; then
  if [ -f .env ]; then
    set -a; source .env; set +a
  fi
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "❌ OPENAI_API_KEY 未设置。先 export OPENAI_API_KEY=your-key"
  echo "   或者创建 .env 文件（参考 .env.local.example）"
  exit 1
fi

echo "🚀 启动 AgentSystem on port ${1:-8765}"
exec python -m app.cli start --port "${1:-8765}"
