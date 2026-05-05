#!/bin/bash
# AgentSystem Web Test Server - 一键启动脚本
# 确保正确的启动顺序和环境配置

set -e  # 遇到错误立即退出

echo "=== AgentSystem Web Test Server 启动脚本 ==="
echo ""

# 1. 设置项目路径
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
CONFIG_DIR="$HOME/.config/agentsystem"
CONFIG_FILE="$CONFIG_DIR/config.yaml"

echo "[1/5] 检查项目路径..."
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ 错误: 项目目录不存在: $PROJECT_DIR"
    exit 1
fi
cd "$PROJECT_DIR"
echo "✅ 项目路径: $PROJECT_DIR"

# 2. 检查并激活虚拟环境
echo ""
echo "[2/5] 激活虚拟环境..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "❌ 错误: 虚拟环境不存在: $VENV_DIR"
    exit 1
fi
source "$VENV_DIR/bin/activate"
echo "✅ Python: $(which python3)"
echo "✅ 版本: $(python3 --version)"

# 3. 检查配置文件
echo ""
echo "[3/5] 检查 LLM 配置..."
if [ ! -f "$CONFIG_FILE" ]; then
    echo "⚠️  警告: 配置文件不存在: $CONFIG_FILE"
    echo "   将尝试从环境变量读取配置"
else
    echo "✅ 配置文件: $CONFIG_FILE"
    # 从配置文件读取并设置环境变量（供依赖 env fallback 的模块使用）
    # 使用 shell-safe 的 export 行并在当前 shell 中 eval
    CONFIG_EXPORTS=$(python3 << 'PYEOF'
import shlex
from pathlib import Path

import yaml

config_path = Path.home() / ".config" / "agentsystem" / "config.yaml"
if config_path.exists():
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    model_cfg = cfg.get("model", {}) or {}
    mapping = {
        "OPENAI_API_KEY": model_cfg.get("api_key"),
        "OPENAI_BASE_URL": model_cfg.get("base_url"),
        "OPENAI_MODEL": model_cfg.get("model"),
    }
    for key, value in mapping.items():
        if value:
            print(f"export {key}={shlex.quote(str(value))}")
PYEOF
)
    if [ -n "$CONFIG_EXPORTS" ]; then
        eval "$CONFIG_EXPORTS"
        echo "✅ 已从 config.yaml 导出 OPENAI_* 环境变量"
    else
        echo "⚠️  未在 config.yaml 中找到可导出的 OPENAI_* 配置"
    fi
fi

# 4. 清理旧进程
echo ""
echo "[4/5] 清理旧进程..."
pkill -f "uvicorn.*http_test_server" 2>/dev/null || true
pkill -f "uvicorn.*app.system.http_test_server" 2>/dev/null || true
sleep 1
echo "✅ 旧进程已清理"

# 5. 启动服务
echo ""
echo "[5/5] 启动 Uvicorn 服务..."
PORT=${PORT:-80}
echo "   端口: $PORT"
echo "   主机: 0.0.0.0"
echo ""

# 使用 nohup 后台运行，输出到日志文件
LOG_FILE="/tmp/agent_test_server.log"
nohup uvicorn app.system.http_test_server:app \
    --host 0.0.0.0 \
    --port $PORT \
    --reload \
    > "$LOG_FILE" 2>&1 &

# 等待服务启动
sleep 3

# 检查服务状态
if curl -s http://localhost:$PORT/api/status > /dev/null 2>&1; then
    echo "✅ 服务启动成功!"
    echo ""
    echo "=== 访问地址 ==="
    echo "  本地: http://localhost:$PORT"
    echo "  公网: http://101.34.58.220:$PORT"
    echo ""
    echo "=== 日志文件 ==="
    echo "  tail -f $LOG_FILE"
    echo ""
    echo "=== 测试命令 ==="
    echo "  curl http://localhost:$PORT/api/status"
    echo ""
else
    echo "❌ 服务启动失败，检查日志:"
    echo "  tail -n 50 $LOG_FILE"
    exit 1
fi
