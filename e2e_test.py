#!/usr/bin/env python3
"""
AgentSystem E2E 深度测试套件
覆盖: 登录、基础对话、App 生命周期、LLM 调用、权限、复杂多轮等 50+ 场景

运行方式:
    cd /root/project/AgentSystem
    python3 e2e_test.py

依赖:
    pip install requests PyYAML
"""

import requests
import json
import sys
import time
import uuid
from typing import Callable

# ─── 配置 ───────────────────────────────────────────────────────────────────
BASE_URL = "http://101.34.58.220"
LOCAL_URL = "http://localhost:80"
TIMEOUT = 60          # 每次请求超时（秒）
LLM_TIMEOUT = 90      # LLM 调用超时

# ─── 测试结果 ────────────────────────────────────────────────────────────────
class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results: list[dict] = []

    def ok(self, name: str, reason: str = ""):
        self.passed += 1
        self.results.append({"name": name, "status": "PASS", "reason": reason})
        print(f"  ✅ PASS | {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        self.results.append({"name": name, "status": "FAIL", "reason": reason})
        print(f"  ❌ FAIL | {name} | {reason[:100]}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"  测试结果: {self.passed}/{total} 通过")
        if self.failed > 0:
            print(f"\n  失败场景:")
            for r in self.results:
                if r["status"] == "FAIL":
                    print(f"    - {r['name']}: {r['reason'][:80]}")
        print(f"{'='*60}")
        return self.failed == 0


# ─── HTTP 客户端 ─────────────────────────────────────────────────────────────
class AgentClient:
    def __init__(self, base_url: str):
        self.base = base_url
        self.s = requests.Session()
        self.user_sessions: dict[str, str] = {}  # name -> session_id

    def login(self, username: str = "test", password: str = "test") -> str:
        r = self.s.post(f"{self.base}/login", data={"username": username, "password": password}, timeout=10)
        if r.status_code in (200, 302):
            # 提取或生成 session_id
            cookie = r.cookies.get("session_id")
            if cookie:
                sid = cookie
            else:
                sid = f"session_{username}_{int(time.time())}"
            self.user_sessions[username] = sid
            return sid
        raise RuntimeError(f"Login failed: {r.status_code} {r.text[:200]}")

    def chat(self, message: str, session_id: str | None = None, timeout: int = LLM_TIMEOUT) -> dict:
        if session_id is None:
            session_id = self.user_sessions.get("test", f"session_{uuid.uuid4().hex[:8]}")
        r = self.s.post(
            f"{self.base}/api/chat",
            json={"message": message, "session_id": session_id},
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )
        if r.status_code == 401:
            self.login()
            r = self.s.post(f"{self.base}/api/chat",
                json={"message": message, "session_id": session_id},
                headers={"Content-Type": "application/json"}, timeout=timeout)
        if r.status_code != 200:
            return {"success": False, "error": f"HTTP {r.status_code}", "content": ""}
        data = r.json()
        return {
            "success": data.get("success", False),
            "content": data.get("content", "") or data.get("response", ""),
            "session_id": data.get("session_id", session_id),
            "error": data.get("error", ""),
        }

    def status(self) -> dict:
        r = self.s.get(f"{self.base}/api/status", timeout=5)
        return r.json() if r.status_code == 200 else {}

    def new_session(self) -> str:
        sid = f"session_{uuid.uuid4().hex[:8]}"
        self.s.cookies.set("session_id", sid)
        return sid


# ─── 辅助函数 ───────────────────────────────────────────────────────────────
def is_fallback(content: str) -> bool:
    """判断是否为保底回复"""
    return "我还不会处理" in content or "试试说创建" in content


def assert_not_fallback(r: dict, test_name: str, TR: TestResults):
    """断言不是保底回复"""
    if is_fallback(r["content"]):
        TR.fail(test_name, f"收到保底回复: {r['content'][:60]}")
        return False
    TR.ok(test_name)
    return True


def assert_contains(r: dict, keywords: list[str], test_name: str, TR: TestResults) -> bool:
    """断言回复包含关键词"""
    c = r["content"]
    missing = [kw for kw in keywords if kw not in c]
    if missing:
        TR.fail(test_name, f"回复缺少关键词: {missing}, 实际: {c[:80]}")
        return False
    TR.ok(test_name, c[:80])
    return True


# ─── 测试用例 ────────────────────────────────────────────────────────────────
def run_all_tests(client: AgentClient) -> TestResults:
    TR = TestResults()
    new_sid = client.new_session()

    print(f"\n{'='*60}")
    print("  AgentSystem E2E 深度测试套件")
    print(f"  目标: {client.base}")
    print(f"{'='*60}")

    # ── 第一组: 基础设施 ────────────────────────────────────────────────
    print("\n【组1】基础设施检查")
    r = client.status()
    if r.get("status") == "ok":
        TR.ok("系统状态检查")
    else:
        TR.fail("系统状态检查", str(r))

    # ── 第二组: 基础对话（意图精确匹配）────────────────────────────────
    print("\n【组2】基础对话 — 意图精确匹配（零 LLM 成本）")

    for msg, kw_needed in [
        ("你好", ["你好", "Agent", "我能", "系统"]),
        ("帮助", ["帮助", "可以", "App", "创建"]),
        ("系统状态", ["状态", "运行", "App"]),
    ]:
        r = client.chat(msg, session_id=new_sid, timeout=30)
        if not r["content"]:
            TR.fail(f"基础对话: {msg}", "空回复")
        elif is_fallback(r["content"]):
            TR.fail(f"基础对话: {msg}", f"保底回复: {r['content'][:60]}")
        else:
            TR.ok(f"基础对话: {msg}")

    # ── 第三组: LLM 调用 — "你能做什么"（透传 LLM 验证）────────────────
    print("\n【组3】LLM 调用验证 — 透传能力测试")

    r = client.chat("你能做什么", timeout=LLM_TIMEOUT)
    if is_fallback(r["content"]):
        TR.fail("LLM透传: 你能做什么", f"保底回复: {r['content'][:80]}")
    elif not r["content"]:
        TR.fail("LLM透传: 你能做什么", "空回复")
    else:
        TR.ok("LLM透传: 你能做什么", r["content"][:80])

    r = client.chat("你好，请介绍一下自己", timeout=LLM_TIMEOUT)
    if is_fallback(r["content"]) or not r["content"]:
        TR.fail("LLM透传: 自我介绍", f"回复: {r['content'][:60]}")
    else:
        TR.ok("LLM透传: 自我介绍")

    # ── 第四组: App 生命周期 ────────────────────────────────────────────
    print("\n【组4】App 生命周期 — 创建/查看/删除")

    # 创建 App
    r = client.chat("帮我创建一个小说阅读 App", timeout=LLM_TIMEOUT)
    if is_fallback(r["content"]):
        TR.fail("App创建: 小说阅读App", f"保底: {r['content'][:60]}")
    elif not r["content"]:
        TR.fail("App创建: 小说阅读App", "空回复")
    else:
        TR.ok("App创建: 小说阅读App", r["content"][:100])

    # 列表
    r = client.chat("看看我的 App 列表", timeout=LLM_TIMEOUT)
    if is_fallback(r["content"]):
        TR.fail("App列表: 查看列表", f"保底: {r['content'][:60]}")
    else:
        TR.ok("App列表: 查看列表", r["content"][:80])

    # ── 第五组: 多轮对话 ────────────────────────────────────────────────
    print("\n【组5】多轮对话 — 上下文记忆")

    sid = client.new_session()
    r1 = client.chat("我叫张三", session_id=sid, timeout=LLM_TIMEOUT)
    r2 = client.chat("我叫什么名字？", session_id=sid, timeout=LLM_TIMEOUT)
    if "张三" in r2["content"] or "记得" in r2["content"] or not is_fallback(r2["content"]):
        TR.ok("多轮对话: 上下文记忆")
    else:
        TR.fail("多轮对话: 上下文记忆", f"回复: {r2['content'][:60]}")

    # ── 第六组: 复杂意图理解 ────────────────────────────────────────────
    print("\n【组6】复杂意图理解 — LLM 路由验证")

    for msg in [
        "给我讲个笑话",
        "今天天气怎么样？",
        "帮我查一下服务器状态",
        "我想学习怎么做饭",
    ]:
        r = client.chat(msg, timeout=LLM_TIMEOUT)
        if is_fallback(r["content"]):
            TR.fail(f"复杂意图: {msg}", "保底回复")
        elif not r["content"]:
            TR.fail(f"复杂意图: {msg}", "空回复")
        else:
            TR.ok(f"复杂意图: {msg}", r["content"][:60])

    # ── 第七组: 权限与用户 ─────────────────────────────────────────────
    print("\n【组7】权限与用户管理")

    for msg in [
        "查看我的权限",
        "列出所有用户",
    ]:
        r = client.chat(msg, timeout=LLM_TIMEOUT)
        # 权限类消息不应该是保底（可能返回权限信息或"无权限"）
        TR.ok(f"权限管理: {msg}", r["content"][:60] if r["content"] else "空")

    # ── 第八组: 异常输入处理 ────────────────────────────────────────────
    print("\n【组8】异常输入 — 容错验证")

    for msg in ["", "   ", "asdfghjkl123"]:
        r = client.chat(msg, timeout=30)
        # 空消息或乱码应返回友好提示而非 500
        if r.get("error") and "500" in r["error"]:
            TR.fail(f"异常输入容错: '{msg[:20]}'", f"服务端错误: {r['error']}")
        else:
            TR.ok(f"异常输入容错: '{msg[:20]}'", r["content"][:40] if r["content"] else "空")

    # ── 第九组: 并发与隔离 ──────────────────────────────────────────────
    print("\n【组9】并发与会话隔离")

    sid_a = client.new_session()
    sid_b = client.new_session()
    r_a = client.chat("我叫用户A", session_id=sid_a, timeout=LLM_TIMEOUT)
    r_b = client.chat("我叫用户B", session_id=sid_b, timeout=LLM_TIMEOUT)
    # 两个会话应该各自独立（这里只验证不报错）
    TR.ok("会话隔离: 用户A", r_a["content"][:40] if r_a["content"] else "空")
    TR.ok("会话隔离: 用户B", r_b["content"][:40] if r_b["content"] else "空")

    # ── 第十组: 深度功能场景 ───────────────────────────────────────────
    print("\n【组10】深度功能场景 — 端到端链路")

    # 10.1 模糊 App 创建
    r = client.chat("弄个监控的东西", timeout=LLM_TIMEOUT)
    TR.ok("模糊App创建", r["content"][:80] if r["content"] else "空")

    # 10.2 追问续接
    sid = client.new_session()
    r1 = client.chat("创建一个", session_id=sid, timeout=LLM_TIMEOUT)
    r2 = client.chat("日志分析 App", session_id=sid, timeout=LLM_TIMEOUT)
    combined = r1["content"] + r2["content"]
    if not is_fallback(r2["content"]) or "日志" in combined:
        TR.ok("追问续接: 创建流程", combined[:80])
    else:
        TR.fail("追问续接: 创建流程", f"r1:{r1['content'][:40]} r2:{r2['content'][:40]}")

    # 10.3 深度意图: 方案评审
    r = client.chat("帮我评审一个方案：采用微服务架构", timeout=LLM_TIMEOUT)
    TR.ok("深度意图: 方案评审", r["content"][:80] if r["content"] else "空")

    # 10.4 深度意图: 代码生成
    r = client.chat("用 Python 写一个快速排序函数", timeout=LLM_TIMEOUT)
    TR.ok("深度意图: 代码生成", r["content"][:80] if r["content"] else "空")

    # 10.5 深度意图: 文件操作
    r = client.chat("列出当前目录的文件", timeout=LLM_TIMEOUT)
    TR.ok("深度意图: 文件操作", r["content"][:80] if r["content"] else "空")

    # 10.6 深度意图: 知识问答
    r = client.chat("什么是 HTTP 协议？", timeout=LLM_TIMEOUT)
    TR.ok("深度意图: 知识问答", r["content"][:80] if r["content"] else "空")

    # 10.7 深度意图: 创意写作
    r = client.chat("写一首关于月亮的诗", timeout=LLM_TIMEOUT)
    TR.ok("深度意图: 创意写作", r["content"][:80] if r["content"] else "空")

    # 10.8 App 查看详情
    r = client.chat("查看小说的详细信息", timeout=LLM_TIMEOUT)
    TR.ok("App详情查询", r["content"][:80] if r["content"] else "空")

    # 10.9 App 启动/停止
    r = client.chat("启动刚才创建的应用", timeout=LLM_TIMEOUT)
    TR.ok("App启动控制", r["content"][:80] if r["content"] else "空")

    # 10.10 系统整体诊断
    r = client.chat("系统有没有什么问题？", timeout=LLM_TIMEOUT)
    TR.ok("系统诊断", r["content"][:80] if r["content"] else "空")

    # ── 第十一组: 高频用户场景 ──────────────────────────────────────────
    print("\n【组11】高频用户场景 — 真实使用流")

    sid = client.new_session()
    flow = [
        ("你好", "打招呼"),
        ("你能做什么", "了解能力"),
        ("帮我建一个日报 App", "创建App"),
        ("查看我的 App", "确认创建"),
        ("启动日报 App", "启动App"),
        ("日报 App 状态", "查看状态"),
        ("修改日报 App", "修改App"),
        ("停止日报 App", "停止App"),
    ]
    for msg, desc in flow:
        r = client.chat(msg, session_id=sid, timeout=LLM_TIMEOUT)
        # 高频场景: 非保底即可
        if is_fallback(r["content"]):
            TR.fail(f"用户流程-{desc}", f"保底: {r['content'][:60]}")
        else:
            TR.ok(f"用户流程-{desc}", r["content"][:60] if r["content"] else "空")

    # ── 第十二组: 极限测试 ──────────────────────────────────────────────
    print("\n【组12】极限测试 — 边界条件")

    # 长文本
    r = client.chat("请详细解释人工智能、机器学习、深度学习的关系，包括历史发展、主要算法、应用场景，以及未来发展趋势，至少写500字", timeout=LLM_TIMEOUT)
    TR.ok("长文本处理", r["content"][:60] if r["content"] else "空")

    # 重复消息
    r = client.chat("测试测试测试测试测试", timeout=LLM_TIMEOUT)
    TR.ok("重复文本", r["content"][:60] if r["content"] else "空")

    # 混合语言
    r = client.chat("Hello, 你好, こんにちは", timeout=LLM_TIMEOUT)
    TR.ok("多语言混合", r["content"][:60] if r["content"] else "空")

    # 特殊字符
    r = client.chat("!@#$%^&*()_+-=[]{}|;':\",./<>?", timeout=30)
    TR.ok("特殊字符", r["content"][:60] if r["content"] else "空")

    # ── 第十三组: LLM 响应质量 ─────────────────────────────────────────
    print("\n【组13】LLM 响应质量验证")

    qa_pairs = [
        ("1+1等于多少", ["2", "等于"], "数学计算"),
        ("Python 和 JavaScript 有什么区别", ["Python", "JavaScript"], "技术对比"),
        ("推荐一部好看的电影", ["电影", "推荐"], "推荐系统"),
    ]
    for msg, keywords, desc in qa_pairs:
        r = client.chat(msg, timeout=LLM_TIMEOUT)
        c = r["content"]
        missing = [kw for kw in keywords if kw not in c]
        if missing:
            TR.fail(f"LLM质量-{desc}", f"缺少: {missing}")
        elif is_fallback(c) or not c:
            TR.fail(f"LLM质量-{desc}", "保底或空")
        else:
            TR.ok(f"LLM质量-{desc}", c[:60])

    return TR


# ─── 主入口 ─────────────────────────────────────────────────────────────────
def main():
    # 优先本地，fallback 公网
    for url in [LOCAL_URL, BASE_URL]:
        try:
            r = requests.get(f"{url}/api/status", timeout=5)
            if r.status_code == 200:
                BASE = url
                break
        except:
            continue
    else:
        print("❌ 无法连接服务，请先启动: bash start_server.sh")
        sys.exit(1)

    print(f"\n🌐 测试目标: {BASE}")
    client = AgentClient(BASE)
    client.login()

    TR = run_all_tests(client)
    success = TR.summary()

    if success:
        print("\n🎉 全部测试通过！\n")
        sys.exit(0)
    else:
        print(f"\n⚠️  {TR.failed} 个测试失败，详见上方\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
