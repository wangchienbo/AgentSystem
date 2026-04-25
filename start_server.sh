#!/bin/bash
# ============================================================
# AgentSystem 一键启动脚本
# 1. 检查依赖和配置
# 2. 清理旧进程
# 3. 启动 AgentSystem 服务（端口 80）
# 4. 等待就绪并验证
# ============================================================

set -e

PROJECT_DIR="/root/project/AgentSystem"
VENV_DIR="$PROJECT_DIR/.venv"
CONFIG_FILE="$HOME/.config/agentsystem/config.yaml"
PORT=${PORT:-80}
LOG_FILE="/tmp/agent_startup.log"

# 颜色
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║     AgentSystem 一键启动脚本                      ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# ---- 1. 检查项目路径 ----
info "[1/6] 检查项目路径..."
if [ ! -d "$PROJECT_DIR" ]; then
    echo $PROJECT_DIR
    error "项目目录不存在: $PROJECT_DIR"
    exit 1
fi
cd "$PROJECT_DIR"
info "  项目目录: $PROJECT_DIR"

# ---- 2. 激活虚拟环境 ----
info "[2/6] 激活虚拟环境..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    error "虚拟环境不存在: $VENV_DIR"
    exit 1
fi
source "$VENV_DIR/bin/activate"
  export PYTHONPATH="$PROJECT_DIR"
info "  Python: $(which python3)"
info "  版本: $(python3 --version | awk '{print $2}')"

# ---- 3. 检查配置文件（ModelRouter 需要） ----
info "[3/6] 检查 LLM 配置文件..."
if [ ! -f "$CONFIG_FILE" ]; then
    error "配置文件不存在: $CONFIG_FILE"
    error "ModelRouter 需要此文件来读取 API 配置"
    exit 1
fi
# 从配置文件提取关键信息用于日志
python3 << PYEOF
import yaml
try:
    cfg = yaml.safe_load(open("$CONFIG_FILE"))
    model = cfg.get("model", {})
    base_url = model.get("base_url", "未配置")
    api_key = model.get("api_key", "未配置")
    api_key_display = api_key[:20] + "..." if api_key and len(api_key) > 20 else api_key
    model_name = model.get("model", "未配置")
    print(f"  配置文件: $CONFIG_FILE")
    print(f"  Base URL: {base_url}")
    print(f"  API Key:  {api_key_display}")
    print(f"  模型:     {model_name}")
    if not api_key or api_key == "未配置":
        print("  ⚠️  警告: api_key 未配置，LLM 调用将失败")
except Exception as e:
    print(f"  ⚠️  读取配置失败: {e}")
PYEOF

# ---- 4. 检查端口占用 ----
info "[4/6] 检查端口 $PORT..."
if lsof -i :$PORT > /dev/null 2>&1; then
    warn "端口 $PORT 已被占用，尝试清理..."
    pkill -f "uvicorn.*http_test_server" 2>/dev/null || true
    sleep 2
    if lsof -i :$PORT > /dev/null 2>&1; then
        PID=$(lsof -t -i :$PORT)
        warn "强制终止进程 PID=$PID"
        kill -9 $PID 2>/dev/null || true
        sleep 1
    fi
    info "  端口已清理"
else
    info "  端口 $PORT 可用"
fi

# ---- 5. 启动服务 ----
info "[5/6] 启动 Uvicorn 服务..."
info "  命令: uvicorn app.system.http_test_server:app --host 0.0.0.0 --port $PORT"
info "  日志: $LOG_FILE"

uvicorn app.system.http_test_server:app \
    --host 0.0.0.0 \
    --port $PORT \
    --reload \
    > "$LOG_FILE" 2>&1 &

STARTUP_PID=$!
info "  进程 PID: $STARTUP_PID"

# ---- 6. 等待就绪并验证 ----
info "[6/6] 等待服务就绪..."
MAX_WAIT=90
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:$PORT/api/status > /dev/null 2>&1; then
        info "✅ 服务启动成功！"
        break
    fi
    sleep 1
    WAITED=$((WAITED + 1))
    echo -n "."
done
echo ""

if [ $WAITED -ge $MAX_WAIT ]; then
    error "服务启动超时（${MAX_WAIT}s），检查日志:"
    tail -30 "$LOG_FILE"
    exit 1
fi

# 最终验证
STATUS=$(curl -s http://localhost:$PORT/api/status)
info "  状态响应: $STATUS"

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║  ✅ AgentSystem 已启动                             ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""
echo "  📍 访问地址"
echo "     本地:  http://localhost:$PORT"
echo "     公网:  http://101.34.58.220:$PORT"
echo ""
echo "  📋 常用命令"
echo "     查看日志:  tail -f $LOG_FILE"
echo "     停止服务:  bash $PROJECT_DIR/stop_server.sh"
echo "     运行测试:  python3 $PROJECT_DIR/e2e_test.py"
echo ""
