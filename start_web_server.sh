#!/bin/bash
# AgentSystem Web Test Server - 一键启动脚本
# 确保正确的启动顺序和环境配置

set -e  # 遇到错误立即退出

echo "=== AgentSystem Web Test Server 启动脚本 ==="
echo ""

# 1. 设置项目路径
PROJECT_DIR="/root/project/AgentSystem"
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
    # 从配置文件读取并设置环境变量（供 http_test_server 使用）
    # 使用 Python 解析 YAML 并导出环境变量
    python3 << 'PYEOF'
import yaml, os, sys
from pathlib import Path

config_path = Path.home() / ".config" / "agentsystem" / "config.yaml"
if config_path.exists():
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    
    # 提取 OpenAI 配置
    model_cfg = cfg.get("model", {})
    if model_cfg.get("api_key"):
        os.environ["OPENAI_API_KEY"] = model_cfg["api_key"]
        print(f"export OPENAI_API_KEY={model_cfg['api_key'][:20]}...")
    if model_cfg.get("base_url"):
        os.environ["OPENAI_BASE_URL"] = model_cfg["base_url"]
        print(f"export OPENAI_BASE_URL={model_cfg['base_url']}")
    if model_cfg.get("model"):
        os.environ["OPENAI_MODEL"] = model_cfg["model"]
        print(f"export OPENAI_MODEL={model_cfg['model']}")
PYEOF
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
