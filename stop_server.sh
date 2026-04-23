#!/bin/bash
# AgentSystem 一键停止脚本

PROJECT_DIR="/root/project/AgentSystem"
PORT=${PORT:-80}
LOG_FILE="/tmp/agent_startup.log"

echo "=== AgentSystem 停止脚本 ==="
echo ""

# 停止 uvicorn
echo "[1/3] 查找并停止 Uvicorn 进程..."
PIDS=$(pgrep -f "uvicorn.*http_test_server" || true)
if [ -n "$PIDS" ]; then
    echo "  发现进程: $PIDS"
    kill $PIDS 2>/dev/null || true
    sleep 2
    # 检查是否还在
    if pgrep -f "uvicorn.*http_test_server" > /dev/null; then
        echo "  强制终止..."
        pkill -9 -f "uvicorn.*http_test_server" 2>/dev/null || true
    fi
    echo "  ✅ 已停止"
else
    echo "  ℹ️  未发现运行中的 Uvicorn 进程"
fi

# 检查端口
echo ""
echo "[2/3] 检查端口 $PORT..."
if lsof -i :$PORT > /dev/null 2>&1; then
    PID=$(lsof -t -i :$PORT)
    echo "  端口 $PORT 被 PID $PID 占用，强制终止..."
    kill -9 $PID 2>/dev/null || true
    sleep 1
    echo "  ✅ 端口已释放"
else
    echo "  ✅ 端口 $PORT 已空闲"
fi

# 备份日志
echo ""
echo "[3/3] 备份日志..."
if [ -f "$LOG_FILE" ]; then
    BACKUP="/tmp/agent_test_$(date +%Y%m%d_%H%M%S).log"
    cp "$LOG_FILE" "$BACKUP"
    echo "  日志已备份: $BACKUP"
fi

echo ""
echo "✅ 服务已停止"
