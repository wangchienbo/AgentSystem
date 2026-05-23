#!/bin/bash
# ═══════════════════════════════════════════════════════
# AgentSystem 一键安装启动脚本
#
# 用法:
#   ./setup_and_start.sh              # 安装 + 启动（默认端口 80）
#   ./setup_and_start.sh --port 8765  # 指定端口
#   ./setup_and_start.sh --install-only  # 只安装不启动
# ═══════════════════════════════════════════════════════

set -e

cd "$(dirname "$0")"
REPO_ROOT="$(pwd)"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── 参数解析 ──
PORT=80
INSTALL_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        --install-only) INSTALL_ONLY=true; shift ;;
        -h|--help)
            echo "用法: $0 [--port PORT] [--install-only]"
            echo "  --port PORT       服务端口（默认 80）"
            echo "  --install-only    只安装不启动"
            exit 0
            ;;
        *) log_error "未知参数: $1"; exit 1 ;;
    esac
done

# ── 系统检查 ──
log_info "检查系统环境..."

# Python
if ! command -v python3 &>/dev/null; then
    log_error "未找到 python3，请先安装 Python 3.11+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    log_error "Python 版本 $PYTHON_VERSION 太低，需要 3.11+"
    exit 1
fi
log_info "Python $PYTHON_VERSION ✅"

# ── 虚拟环境 ──
if [ ! -d ".venv" ]; then
    log_info "创建虚拟环境 .venv..."
    python3 -m venv .venv
else
    log_info "虚拟环境已存在"
fi

source .venv/bin/activate

# ── 安装依赖 ──
log_info "安装项目依赖..."
pip install -e .[dev] --quiet
log_info "依赖安装完成 ✅"

# ── 配置检查 ──
log_info "检查配置..."

CONFIG_FILE="$HOME/.config/agentsystem/config.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    log_warn "配置文件不存在: $CONFIG_FILE"
    
    # 尝试从示例文件复制
    if [ -f "config/config.local.example.yaml" ]; then
        mkdir -p "$(dirname "$CONFIG_FILE")"
        cp "config/config.local.example.yaml" "$CONFIG_FILE"
        log_warn "已从示例文件创建配置，请编辑 $CONFIG_FILE 填入 API Key"
    fi
fi

# 检查 OPENAI_API_KEY 环境变量
if [ -z "${OPENAI_API_KEY:-}" ] && [ -f ".env" ]; then
    set -a; source .env; set +a
    log_info "已从 .env 加载环境变量"
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
    log_warn "OPENAI_API_KEY 未设置"
    log_warn "请先 export OPENAI_API_KEY=your-key 或创建 .env 文件"
    if [ "$INSTALL_ONLY" = true ]; then
        log_info "安装模式，跳过启动检查"
        exit 0
    fi
    read -p "是否继续启动？(y/N) " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        log_info "已取消启动"
        exit 0
    fi
fi

# ── Bootstrap 运行时布局 ──
log_info "初始化运行时布局..."
python -m app.cli bootstrap --quiet 2>/dev/null || true

# ── 启动 ──
if [ "$INSTALL_ONLY" = true ]; then
    log_info "安装完成！"
    log_info "启动命令: python -m app.cli start --port $PORT"
    exit 0
fi

log_info "🚀 启动 AgentSystem on port $PORT..."
exec python -m app.cli start --port "$PORT"
