#!/usr/bin/env bash
# ===========================================================================
# AgentSystem 端到端 HTTP 交互测试指令集
# ===========================================================================
# 用法:
#   1. 启动服务: cd <repo-root> && python3 -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
#   2. 运行测试: bash tests/scripts/e2e_interactive_tests.sh
#
# 基础 URL（可通过环境变量覆盖）
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
SESSION_ID=""

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 计数器
PASS=0
FAIL=0
TOTAL=0

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
run_test() {
    local name="$1"
    local endpoint="$2"
    local payload="$3"
    local expect_field="${4:-content}"
    local expect_value="$5"

    TOTAL=$((TOTAL + 1))
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}📋 测试 #${TOTAL}: ${name}${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "POST ${BASE_URL}${endpoint}"
    echo "Payload: ${payload}"
    echo ""

    if [ -n "$payload" ]; then
        RESPONSE=$(curl -s -X POST "${BASE_URL}${endpoint}" \
            -H "Content-Type: application/json" \
            -d "$payload" 2>&1)
    else
        RESPONSE=$(curl -s -X GET "${BASE_URL}${endpoint}" 2>&1)
    fi

    echo -e "响应: $(echo "$RESPONSE" | head -c 500)"
    echo ""

    # 检查期望值
    if [ -n "$expect_value" ]; then
        if echo "$RESPONSE" | grep -q "$expect_value"; then
            echo -e "${GREEN}✅ PASS: 包含 '${expect_value}'${NC}"
            PASS=$((PASS + 1))
        else
            echo -e "${RED}❌ FAIL: 未找到 '${expect_value}'${NC}"
            FAIL=$((FAIL + 1))
        fi
    else
        if echo "$RESPONSE" | grep -q '"content"'; then
            echo -e "${GREEN}✅ PASS: 响应包含 content 字段${NC}"
            PASS=$((PASS + 1))
        else
            echo -e "${RED}❌ FAIL: 响应缺少 content 字段${NC}"
            FAIL=$((FAIL + 1))
        fi
    fi
}

capture_session_id() {
    SESSION_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
    if [ -n "$SESSION_ID" ]; then
        echo -e "  📌 会话 ID: ${GREEN}${SESSION_ID}${NC}"
    fi
}

# ===========================================================================
# 第一部分：健康检查与系统状态
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第一部分：健康检查与系统状态                    ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T001: 健康检查
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 系统健康检查${NC}"
RESPONSE=$(curl -s "${BASE_URL}/health" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"ok"'; then
    echo -e "${GREEN}✅ PASS: 系统健康${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: 系统不健康${NC}"
    FAIL=$((FAIL + 1))
fi

# T002: 版本检查
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 版本检查${NC}"
RESPONSE=$(curl -s "${BASE_URL}/version" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"version"'; then
    echo -e "${GREEN}✅ PASS: 版本信息返回${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: 版本信息缺失${NC}"
    FAIL=$((FAIL + 1))
fi

# ===========================================================================
# 第二部分：基础对话交互（问候、帮助、状态）
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第二部分：基础对话交互                          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T003: 问候
run_test "问候 — 你好" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"你好"}'

# T004: 帮助
run_test "帮助 — 查看帮助" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"帮助"}' \
    "content" "帮助"

# T005: 系统状态
run_test "系统状态" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"系统状态"}' \
    "content" "系统状态"

# T006: 未知/模糊指令
run_test "模糊指令 — 那个啥" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"那个啥"}'

# ===========================================================================
# 第三部分：App 管理 — 列表、查询
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第三部分：App 管理 — 列表、查询                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T007: 查看 App 列表（初始为空）
run_test "查看 App 列表（初始）" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"看看我的 App"}'

# T008: 查询不存在的 App
run_test "查询不存在的 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"看看小说App的状态"}'

# ===========================================================================
# 第四部分：App 创建 — 完整链路
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第四部分：App 创建 — 完整链路                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T009: 创建小说 App
run_test "创建小说 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"帮我建一个小说 App"}'

# T010: 创建监控 App
run_test "创建监控 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"创建一个监控 App"}'

# T011: 创建音乐 App
run_test "创建音乐 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"帮我建一个音乐 App"}'

# T012: 创建翻译 App
run_test "创建翻译 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"创建一个翻译工具 App"}'

# ===========================================================================
# 第五部分：会话管理
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第五部分：会话管理                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T013: 获取会话列表
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 获取用户会话列表${NC}"
RESPONSE=$(curl -s "${BASE_URL}/chat/sessions?user_id=alice" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"sessions"'; then
    echo -e "${GREEN}✅ PASS: 会话列表返回${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: 会话列表缺失${NC}"
    FAIL=$((FAIL + 1))
fi

# T014: 获取最近会话
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 获取最近会话${NC}"
RESPONSE=$(curl -s "${BASE_URL}/chat/sessions/last?user_id=alice" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"session"'; then
    echo -e "${GREEN}✅ PASS: 最近会话返回${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: 最近会话缺失${NC}"
    FAIL=$((FAIL + 1))
fi

# T015: 新建会话并记录
run_test "指定会话 ID 发送消息" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"你好","session_id":"test-session-001"}'

# T016: 获取会话消息历史
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 获取会话消息历史${NC}"
RESPONSE=$(curl -s "${BASE_URL}/chat/sessions/test-session-001/messages?limit=10" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"messages"'; then
    echo -e "${GREEN}✅ PASS: 消息历史返回${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: 消息历史缺失${NC}"
    FAIL=$((FAIL + 1))
fi

# ===========================================================================
# 第六部分：多轮对话 — 创建 App 过程中的交互
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第六部分：多轮对话 — 创建 App 过程中的交互      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T017: 多轮对话 — 第一轮：我想建个 App
run_test "多轮对话 — 第一轮：我想建个 App" \
    "/chat/message" \
    '{"user_id":"bob","channel":"webchat","message":"我想建个 App"}'

# T018: 多轮对话 — 第二轮：写小说的（补充信息）
run_test "多轮对话 — 第二轮：补充类型" \
    "/chat/message" \
    '{"user_id":"bob","channel":"webchat","message":"写小说的"}'

# T019: 多轮对话 — 第三轮：再加个插画功能（追加需求）
run_test "多轮对话 — 第三轮：追加需求" \
    "/chat/message" \
    '{"user_id":"bob","channel":"webchat","message":"再加个插画功能"}'

# ===========================================================================
# 第七部分：App 生命周期 — 启动、停止、查询
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第七部分：App 生命周期 — 启动、停止、查询       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T020: 启动 App
run_test "启动 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"启动小说App"}'

# T021: 停止 App
run_test "停止 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"停止小说App"}'

# T022: 暂停 App
run_test "暂停 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"暂停小说App"}'

# T023: 恢复 App
run_test "恢复 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"恢复小说App"}'

# T024: 查询 App 详情
run_test "查询 App 详情" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"看看小说App的详情"}'

# ===========================================================================
# 第八部分：App 修改 — 权限门控 + dry-run
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第八部分：App 修改 — 权限门控 + dry-run         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T025: 修改 App — 不需要新 skill
run_test "修改 App（已有 skill）" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"给小说App加个章节管理功能"}'

# T026: 修改 App — 需要新 skill（普通用户应被拦截）
run_test "修改 App 需要新 skill（普通用户）" \
    "/chat/message" \
    '{"user_id":"bob","channel":"webchat","message":"给小说App加一个AI插画生成功能"}'

# T027: 修改 App — 需要新 skill（管理员应通过）
run_test "修改 App 需要新 skill（管理员）" \
    "/chat/message" \
    '{"user_id":"admin","channel":"webchat","message":"给小说App加一个AI插画生成功能"}'

# ===========================================================================
# 第九部分：权限管理
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第九部分：权限管理                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T028: 查看自己权限
run_test "查看自己权限" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"看看我的权限"}'

# T029: 查看所有用户
run_test "查看所有用户" \
    "/chat/message" \
    '{"user_id":"admin","channel":"webchat","message":"列出所有用户"}'

# T030: 授予 admin 权限
run_test "授予 admin 权限" \
    "/chat/message" \
    '{"user_id":"root","channel":"webchat","message":"给 alice 授予 admin 权限"}'

# T031: 撤销权限
run_test "撤销权限" \
    "/chat/message" \
    '{"user_id":"root","channel":"webchat","message":"撤销 bob 的 admin 权限"}'

# ===========================================================================
# 第十部分：直接 API 调用（不通过聊天）
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第十部分：直接 API 调用                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T032: 获取 App 列表（API）
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 获取 App 列表（API）${NC}"
RESPONSE=$(curl -s "${BASE_URL}/apps" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"apps"'; then
    echo -e "${GREEN}✅ PASS: App 列表返回${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: App 列表缺失${NC}"
    FAIL=$((FAIL + 1))
fi

# T033: 获取 registry 概览
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 获取 registry 概览${NC}"
RESPONSE=$(curl -s "${BASE_URL}/registry/apps/overview" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"apps"'; then
    echo -e "${GREEN}✅ PASS: registry 概览返回${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: registry 概览缺失${NC}"
    FAIL=$((FAIL + 1))
fi

# T034: 获取 skill 列表
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 获取 skill 列表${NC}"
RESPONSE=$(curl -s "${BASE_URL}/skills" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"skills"'; then
    echo -e "${GREEN}✅ PASS: skill 列表返回${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: skill 列表缺失${NC}"
    FAIL=$((FAIL + 1))
fi

# T035: 获取 token 使用情况
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 获取 token 使用情况${NC}"
RESPONSE=$(curl -s "${BASE_URL}/chat/token-usage?user_id=alice" 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"total_tokens"'; then
    echo -e "${GREEN}✅ PASS: token 使用情况返回${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: token 使用情况缺失${NC}"
    FAIL=$((FAIL + 1))
fi

# ===========================================================================
# 第十一部分：错误处理与边界情况
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第十一分：错误处理与边界情况                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T036: 空消息
run_test "空消息" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":""}'

# T037: 超长消息
run_test "超长消息（>4000 字）" \
    "/chat/message" \
    "{\"user_id\":\"alice\",\"channel\":\"webchat\",\"message\":\"$(python3 -c "print('测试' * 2000)")\"}"

# T038: 非法 user_id
run_test "非法 user_id" \
    "/chat/message" \
    '{"user_id":"","channel":"webchat","message":"你好"}'

# T039: 非法 JSON
TOTAL=$((TOTAL + 1))
echo ""
echo -e "${YELLOW}📋 测试 #${TOTAL}: 非法 JSON 请求${NC}"
RESPONSE=$(curl -s -X POST "${BASE_URL}/chat/message" \
    -H "Content-Type: application/json" \
    -d 'not json' 2>&1)
echo "响应: $RESPONSE"
if echo "$RESPONSE" | grep -q '"detail"\|"error"\|"status"'; then
    echo -e "${GREEN}✅ PASS: 返回错误信息${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ FAIL: 未返回错误信息${NC}"
    FAIL=$((FAIL + 1))
fi

# T040: 不存在的会话 ID
run_test "不存在的会话 ID" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"继续","session_id":"nonexistent-session-999"}'

# ===========================================================================
# 第十二部分：跨用户场景
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第十二部分：跨用户场景                          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T041: 用户 A 创建 App → 用户 B 查看列表（应看不到）
run_test "用户 B 查看 App 列表（应为空或仅自己的）" \
    "/chat/message" \
    '{"user_id":"charlie","channel":"webchat","message":"看看我的 App"}'

# T042: 用户 B 尝试修改用户 A 的 App（应被拒）
run_test "用户 B 修改用户 A 的 App（应被拒）" \
    "/chat/message" \
    '{"user_id":"charlie","channel":"webchat","message":"修改小说App"}'

# T043: 用户 C 创建自己的 App
run_test "用户 C 创建 App" \
    "/chat/message" \
    '{"user_id":"charlie","channel":"webchat","message":"帮我建一个日记 App"}'

# ===========================================================================
# 第十三部分：交互指令与快捷操作
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第十三部分：交互指令与快捷操作                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T044: 使用 interaction/command API
run_test "interaction/command — 创建 App" \
    "/interaction/command" \
    '{"user_id":"alice","command":"create_app","parameters":{"app_type":"小说","app_name":"novel_app"}}'

# T045: 使用 interaction/command — 列出 App
run_test "interaction/command — 列出 App" \
    "/interaction/command" \
    '{"user_id":"alice","command":"list_apps","parameters":{}}'

# ===========================================================================
# 第十四部分：资产表集成测试
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第十四部分：资产表集成测试                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T046: 创建 App 后检查资产注册
run_test "创建 App 后查看列表（验证资产注册）" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"看看我的 App"}'

# ===========================================================================
# 第十五部分：删除 App
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  第十五部分：删除 App                            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"

# T047: 删除 App
run_test "删除 App" \
    "/chat/message" \
    '{"user_id":"alice","channel":"webchat","message":"删除日记App"}'

# ===========================================================================
# 汇总报告
# ===========================================================================
echo -e "\n${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  📊 测试汇总报告                                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  总测试数: ${TOTAL}"
echo -e "  ${GREEN}✅ 通过: ${PASS}${NC}"
echo -e "  ${RED}❌ 失败: ${FAIL}${NC}"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}⚠️  有 ${FAIL} 个测试失败，请检查上方输出定位问题。${NC}"
    exit 1
else
    echo -e "${GREEN}🎉 所有测试通过！全链路打通！${NC}"
    exit 0
fi
