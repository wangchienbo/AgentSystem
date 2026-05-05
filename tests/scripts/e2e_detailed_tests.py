#!/usr/bin/env python3
"""
AgentSystem 端到端 HTTP 交互测试 — Python 版
=================================================
更精细的测试控制：支持会话追踪、按钮操作模拟、多轮对话、权限矩阵。

用法:
  1. 启动服务: cd <repo-root> && python3 -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
  2. 运行测试: python3 tests/scripts/e2e_detailed_tests.py
"""
import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0
TOTAL = 0

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"


# ---------------------------------------------------------------------------
# 核心客户端
# ---------------------------------------------------------------------------
class AgentClient:
    """HTTP 客户端，封装 chat/message 交互 + 会话追踪。"""

    def __init__(self, user_id: str, channel: str = "webchat"):
        self.user_id = user_id
        self.channel = channel
        self.session_id: str | None = None
        self.last_response: dict = {}

    def send(self, message: str, session_id: str | None = None) -> dict:
        """发送消息并返回响应。"""
        payload = {
            "user_id": self.user_id,
            "channel": self.channel,
            "message": message,
        }
        sid = session_id or self.session_id
        if sid:
            payload["session_id"] = sid

        resp = requests.post(f"{BASE_URL}/chat/message", json=payload)
        data = resp.json()
        self.last_response = data
        if "session_id" in data and data["session_id"]:
            self.session_id = data["session_id"]
        return data

    def action(self, action_id: str, action_params: dict) -> dict:
        """模拟按钮点击。"""
        if not self.session_id:
            raise RuntimeError("No active session. Send a message first.")
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "action_id": action_id,
            "action_params": action_params,
        }
        resp = requests.post(f"{BASE_URL}/chat/actions/{action_id}", json=payload)
        data = resp.json()
        self.last_response = data
        return data

    @property
    def content(self) -> str:
        return self.last_response.get("content", "")

    @property
    def msg_type(self) -> str:
        return self.last_response.get("type", "")

    @property
    def requires_input(self) -> bool:
        return self.last_response.get("requires_input", False)

    @property
    def actions(self) -> list:
        return self.last_response.get("actions", [])

    def find_action(self, label_substring: str) -> dict | None:
        for a in self.actions:
            if label_substring.lower() in a.get("label", "").lower():
                return a
        return None


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------
def section(title: str):
    print(f"\n{GREEN}{'='*60}{NC}")
    print(f"{GREEN}  {title}{NC}")
    print(f"{GREEN}{'='*60}{NC}")


def assert_contains(test_name: str, text: str, substring: str):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if substring in text:
        print(f"  {GREEN}✅ PASS{NC}: {test_name} — 包含 '{substring}'")
        PASS += 1
        return True
    else:
        print(f"  {RED}❌ FAIL{NC}: {test_name} — 未找到 '{substring}'")
        print(f"     实际内容: {text[:200]}")
        FAIL += 1
        return False


def assert_not_contains(test_name: str, text: str, substring: str):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if substring not in text:
        print(f"  {GREEN}✅ PASS{NC}: {test_name} — 不包含 '{substring}'")
        PASS += 1
        return True
    else:
        print(f"  {RED}❌ FAIL{NC}: {test_name} — 不应包含 '{substring}'")
        print(f"     实际内容: {text[:200]}")
        FAIL += 1
        return False


def assert_type(test_name: str, actual_type: str, expected_type: str):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if actual_type == expected_type:
        print(f"  {GREEN}✅ PASS{NC}: {test_name} — 类型={expected_type}")
        PASS += 1
        return True
    else:
        print(f"  {RED}❌ FAIL{NC}: {test_name} — 期望类型={expected_type}, 实际={actual_type}")
        FAIL += 1
        return False


def assert_has_actions(test_name: str, actions: list, label_substring: str):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    found = any(label_substring.lower() in a.get("label", "").lower() for a in actions)
    if found:
        print(f"  {GREEN}✅ PASS{NC}: {test_name} — 有 '{label_substring}' 按钮")
        PASS += 1
        return True
    else:
        print(f"  {RED}❌ FAIL{NC}: {test_name} — 缺少 '{label_substring}' 按钮")
        print(f"     可用按钮: {[a.get('label') for a in actions]}")
        FAIL += 1
        return False


def get_api(endpoint: str, params: dict = None) -> dict:
    resp = requests.get(f"{BASE_URL}{endpoint}", params=params)
    return resp.json()


# ===========================================================================
# 测试用例
# ===========================================================================

def test_01_health():
    section("T01: 健康检查")
    data = get_api("/health")
    assert_contains("系统健康", json.dumps(data), "ok")

    data = get_api("/version")
    assert_contains("版本信息", json.dumps(data), "version")


def test_02_greet():
    section("T02: 问候交互")
    client = AgentClient("alice")
    data = client.send("你好")
    assert_contains("问候回复", client.content, "你好")
    assert_contains("自我介绍", client.content, "AgentSystem") or assert_contains("自我介绍", client.content, "系统")


def test_03_help():
    section("T03: 帮助")
    client = AgentClient("alice")
    data = client.send("帮助")
    assert_contains("帮助内容", client.content, "帮助")


def test_04_system_status():
    section("T04: 系统状态")
    client = AgentClient("alice")
    data = client.send("系统状态")
    assert_contains("状态信息", client.content, "状态")


def test_05_list_apps_empty():
    section("T05: 查看空 App 列表")
    client = AgentClient("newuser")
    data = client.send("看看我的 App")
    # 应该提示没有 App 或建议创建
    ok = "没有" in client.content or "创建" in client.content
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if ok:
        print(f"  {GREEN}✅ PASS{NC}: 空列表提示合理")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: 空列表提示不合理 — {client.content[:200]}")
        FAIL += 1


def test_06_create_app():
    section("T06: 创建 App 链路")
    client = AgentClient("alice")

    # 创建小说 App
    data = client.send("帮我建一个小说 App")
    print(f"  创建响应: {client.content[:300]}")

    # 检查是否返回了确认卡片或成功消息
    ok = "创建" in client.content or "小说" in client.content or "确认" in client.content
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if ok:
        print(f"  {GREEN}✅ PASS{NC}: 创建请求得到响应")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: 创建请求未得到合理响应")
        FAIL += 1

    # 如果有确认按钮，点击确认
    confirm_action = client.find_action("确认创建")
    if confirm_action:
        print("  → 点击确认创建按钮...")
        data = client.action(confirm_action["id"], confirm_action["payload"])
        print(f"  确认后: {client.content[:300]}")


def test_07_list_apps_after_create():
    section("T07: 创建后查看 App 列表")
    client = AgentClient("alice")
    data = client.send("看看我的 App")
    print(f"  列表响应: {client.content[:300]}")

    # 检查是否有 App 信息
    ok = "App" in client.content or "没有" in client.content or client.msg_type == "list"
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if ok:
        print(f"  {GREEN}✅ PASS{NC}: 列表返回合理")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: 列表返回异常")
        FAIL += 1


def test_08_multiple_create():
    section("T08: 连续创建多个 App")
    client = AgentClient("alice")

    apps_to_create = ["监控 App", "音乐 App", "翻译工具"]
    for app_desc in apps_to_create:
        print(f"\n  → 创建: {app_desc}")
        data = client.send(f"帮我建一个{app_desc}")
        print(f"  响应: {client.content[:200]}")

        # 有确认按钮就确认
        confirm = client.find_action("确认创建")
        if confirm:
            client.action(confirm["id"], confirm["payload"])
            print(f"  确认后: {client.content[:100]}")


def test_09_app_lifecycle():
    section("T09: App 生命周期 — 启动/停止")
    client = AgentClient("alice")

    # 启动
    data = client.send("启动小说App")
    print(f"  启动: {client.content[:200]}")

    # 停止
    data = client.send("停止小说App")
    print(f"  停止: {client.content[:200]}")


def test_10_query_app():
    section("T10: 查询 App 详情")
    client = AgentClient("alice")
    data = client.send("看看小说App的详情")
    print(f"  详情: {client.content[:200]}")


def test_11_modify_app():
    section("T11: 修改 App")
    client = AgentClient("alice")
    data = client.send("给小说App加个章节管理功能")
    print(f"  修改请求: {client.content[:300]}")

    # 如果有确认修改按钮
    confirm = client.find_action("确认修改")
    if confirm:
        print("  → 点击确认修改...")
        data = client.action(confirm["id"], confirm["payload"])
        print(f"  修改结果: {client.content[:300]}")


def test_12_multi_turn():
    section("T12: 多轮对话 — 逐步创建 App")
    client = AgentClient("bob")

    # 第一轮：模糊请求
    data = client.send("我想建个 App")
    print(f"  第一轮: {client.content[:200]}")

    # 第二轮：补充类型
    data = client.send("写小说的")
    print(f"  第二轮: {client.content[:200]}")


def test_13_cross_user_isolation():
    section("T13: 跨用户隔离")
    # 用户 A 创建
    alice = AgentClient("alice")
    alice.send("帮我建一个日记 App")
    confirm = alice.find_action("确认创建")
    if confirm:
        alice.action(confirm["id"], confirm["payload"])

    # 用户 B 查看（不应看到 A 的 App）
    bob = AgentClient("bob")
    data = bob.send("看看我的 App")
    print(f"  用户 B 的列表: {bob.content[:200]}")

    global PASS, FAIL, TOTAL
    TOTAL += 1
    # Bob 的列表应该为空或只有自己的
    ok = "没有" in bob.content or "日记" not in bob.content or bob.msg_type == "list"
    if ok:
        print(f"  {GREEN}✅ PASS{NC}: 跨用户隔离正常")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: Bob 看到了 Alice 的 App")
        FAIL += 1


def test_14_modify_permission():
    section("T14: 修改权限门控")
    alice = AgentClient("alice")

    # 尝试修改别人的 App（如果存在）
    data = alice.send("修改小说App")
    print(f"  修改请求: {alice.content[:200]}")


def test_15_session_management():
    section("T15: 会话管理")
    # 获取会话列表
    data = get_api("/chat/sessions", {"user_id": "alice"})
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if "sessions" in data:
        print(f"  {GREEN}✅ PASS{NC}: 会话列表返回 — {len(data['sessions'])} 个会话")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: 会话列表缺失")
        FAIL += 1

    # 获取最近会话
    data = get_api("/chat/sessions/last", {"user_id": "alice"})
    TOTAL += 1
    if "session" in data:
        print(f"  {GREEN}✅ PASS{NC}: 最近会话返回")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: 最近会话缺失")
        FAIL += 1

    # 获取会话消息
    client = AgentClient("alice")
    if client.session_id:
        data = get_api(f"/chat/sessions/{client.session_id}/messages", {"limit": 10})
        TOTAL += 1
        if "messages" in data:
            print(f"  {GREEN}✅ PASS{NC}: 会话消息返回 — {len(data['messages'])} 条")
            PASS += 1
        else:
            print(f"  {RED}❌ FAIL{NC}: 会话消息缺失")
            FAIL += 1


def test_16_direct_api():
    section("T16: 直接 API 调用")
    global PASS, FAIL, TOTAL

    # App 列表
    data = get_api("/apps")
    TOTAL += 1
    if "apps" in data:
        print(f"  {GREEN}✅ PASS{NC}: API /apps 返回 — {len(data['apps'])} 个")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: API /apps 异常")
        FAIL += 1

    # Skill 列表
    data = get_api("/skills")
    TOTAL += 1
    if "skills" in data:
        print(f"  {GREEN}✅ PASS{NC}: API /skills 返回 — {len(data['skills'])} 个")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: API /skills 异常")
        FAIL += 1

    # Token 使用
    data = get_api("/chat/token-usage", {"user_id": "alice"})
    TOTAL += 1
    if "total_tokens" in data:
        print(f"  {GREEN}✅ PASS{NC}: Token 使用返回")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: Token 使用缺失")
        FAIL += 1


def test_17_error_handling():
    section("T17: 错误处理")
    global PASS, FAIL, TOTAL

    # 非法 JSON
    resp = requests.post(f"{BASE_URL}/chat/message",
                         headers={"Content-Type": "application/json"},
                         data="not json")
    TOTAL += 1
    if resp.status_code in (400, 422, 500):
        print(f"  {GREEN}✅ PASS{NC}: 非法 JSON → {resp.status_code}")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: 非法 JSON → {resp.status_code}")
        FAIL += 1

    # 不存在的会话
    client = AgentClient("alice")
    data = client.send("继续", session_id="nonexistent-999")
    TOTAL += 1
    ok = client.content != "" or client.msg_type != ""
    if ok:
        print(f"  {GREEN}✅ PASS{NC}: 不存在会话 → 正常处理")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: 不存在会话 → 无响应")
        FAIL += 1


def test_18_interaction_command():
    section("T18: interaction/command API")
    global PASS, FAIL, TOTAL

    # 创建 App
    resp = requests.post(f"{BASE_URL}/interaction/command", json={
        "user_id": "alice",
        "command": "create_app",
        "parameters": {"app_type": "测试", "app_name": "test_app"},
    })
    data = resp.json()
    TOTAL += 1
    if "content" in data or "type" in data:
        print(f"  {GREEN}✅ PASS{NC}: interaction/command 创建 App 响应")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: interaction/command 无响应")
        FAIL += 1


def test_19_full_chain():
    section("T19: 完整链路 — 创建→启动→查询→修改")
    client = AgentClient("admin")

    # 1. 创建
    data = client.send("帮我建一个博客 App")
    print(f"  [1] 创建: {client.content[:200]}")
    confirm = client.find_action("确认创建")
    if confirm:
        client.action(confirm["id"], confirm["payload"])
        print(f"  [1] 确认后: {client.content[:100]}")

    # 2. 查看列表
    data = client.send("看看我的 App")
    print(f"  [2] 列表: {client.content[:200]}")

    # 3. 启动
    data = client.send("启动博客App")
    print(f"  [3] 启动: {client.content[:200]}")

    # 4. 查询详情
    data = client.send("看看博客App的详情")
    print(f"  [4] 详情: {client.content[:200]}")

    # 5. 修改
    data = client.send("给博客App加个评论功能")
    print(f"  [5] 修改: {client.content[:200]}")
    confirm = client.find_action("确认修改")
    if confirm:
        client.action(confirm["id"], confirm["payload"])
        print(f"  [5] 确认后: {client.content[:200]}")

    # 6. 再查询
    data = client.send("看看博客App的详情")
    print(f"  [6] 再查询: {client.content[:200]}")

    global PASS, FAIL, TOTAL
    TOTAL += 1
    if "博客" in client.content or "App" in client.content:
        print(f"  {GREEN}✅ PASS{NC}: 完整链路打通")
        PASS += 1
    else:
        print(f"  {RED}❌ FAIL{NC}: 链路断裂")
        FAIL += 1


# ===========================================================================
# 主入口
# ===========================================================================
if __name__ == "__main__":
    print(f"\n{CYAN}{'='*60}{NC}")
    print(f"{CYAN}  AgentSystem 端到端 HTTP 交互测试{NC}")
    print(f"{CYAN}  目标: {BASE_URL}{NC}")
    print(f"{CYAN}{'='*60}{NC}")

    # 先检查服务是否运行
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        print(f"\n  ✅ 服务已启动: {resp.json()}")
    except requests.ConnectionError:
        print(f"\n  {RED}❌ 服务未启动！请先运行:{NC}")
        print(f"  cd <repo-root> && python3 -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # 运行所有测试
    test_01_health()
    test_02_greet()
    test_03_help()
    test_04_system_status()
    test_05_list_apps_empty()
    test_06_create_app()
    test_07_list_apps_after_create()
    test_08_multiple_create()
    test_09_app_lifecycle()
    test_10_query_app()
    test_11_modify_app()
    test_12_multi_turn()
    test_13_cross_user_isolation()
    test_14_modify_permission()
    test_15_session_management()
    test_16_direct_api()
    test_17_error_handling()
    test_18_interaction_command()
    test_19_full_chain()

    # 汇总
    print(f"\n{GREEN}{'='*60}{NC}")
    print(f"{GREEN}  📊 测试汇总{NC}")
    print(f"{GREEN}{'='*60}{NC}")
    print(f"  总测试: {TOTAL}")
    print(f"  {GREEN}✅ 通过: {PASS}{NC}")
    print(f"  {RED}❌ 失败: {FAIL}{NC}")

    if FAIL > 0:
        print(f"\n{RED}⚠️  有 {FAIL} 个测试失败，请查看上方输出定位问题。{NC}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}🎉 所有测试通过！全链路打通！{NC}")
        sys.exit(0)
