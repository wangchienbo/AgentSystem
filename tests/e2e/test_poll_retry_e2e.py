"""E2E 锁定：轮询指数退避重试（_pollTaskLoop 网络瞬断不直接失败）
- 拦截第一次 /api/novel/task/* 轮询请求返回 503
- 验证聊天流式最终仍成功（重试生效），且无 JS 错误
用法: python /tmp/e2e_retry.py --base-url http://localhost:8765
"""
import argparse, sys
from playwright.sync_api import sync_playwright

p = argparse.ArgumentParser()
p.add_argument("--base-url", default="http://localhost:8765")
args = p.parse_args()
BASE = args.base_url
passed = []
def check(name, ok, extra=""):
    passed.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name} {extra}")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page()
    console_errors = []
    page.on("console", lambda m: console_errors.append((m.type, m.text)) if m.type == "error" else None)

    # 拦截第一次 /api/novel/task/* 请求 → 503，其余放行（模拟网络瞬断）
    flap = {"count": 0}
    def route_task(route):
        if "/api/novel/task/" in route.request.url and flap["count"] == 0:
            flap["count"] += 1
            print(f"  🧪 模拟网络瞬断: 503 on first poll → {route.request.url.split('?')[0]}")
            route.fulfill(status=503, content_type="application/json", body='{"detail":"flap"}')
        else:
            route.continue_()
    page.route("**/api/novel/task/**", route_task)

    page.goto(f"{BASE}/studio")
    page.wait_for_timeout(1500)
    if page.locator("#loginUser").count() > 0:
        page.fill("#loginUser", "retry_user")
        page.click("#loginBtn")
        page.wait_for_timeout(2000)

    # 进入第一本小说工作室
    page.locator(".card").first.click()
    page.wait_for_timeout(1500)
    check("进入工作室", page.locator("#chat-input").count() > 0)

    # 发送聊天
    page.fill("#chat-input", "讲一下小说的设定？")
    page.click("#send-btn")
    page.wait_for_timeout(500)

    # 等待流式完成（输入框重新启用）
    try:
        page.wait_for_function(
            "document.querySelector('#chat-input') && !document.querySelector('#chat-input').disabled",
            timeout=120 * 1000)
        check("重试后轮询完成(输入框恢复)", True)
    except Exception as e:
        check("重试后轮询完成(输入框恢复)", False, f"timeout {e}")

    page.wait_for_timeout(2500)
    ai = page.locator(".msg.ai")
    ai_text = ai.last.inner_text().strip() if ai.count() else ""
    has_reply = (ai.count() > 0 and len(ai_text) > 0 and not ai_text.startswith("⏳")
                 and "暂无回复" not in ai_text and not ai_text.startswith("⚠️"))
    check("重试后收到AI回复", has_reply, f"AI: {ai_text[:50]!r}")
    check("确实发生过网络瞬断(503拦截)", flap["count"] == 1)

    real = [(t, m) for t, m in console_errors if "favicon" not in m.lower() and "Failed to load resource" not in m]
    if real:
        for t,m in real: print(f"      [console {t}] {m[:120]}")
    check("无JS错误", len(real) == 0, f"{len(real)}")

    b.close()

ok_all = all(x[1] for x in passed)
print(f"\n📊 退避重试 E2E: {sum(1 for _,k in passed if k)}/{len(passed)} 通过")
sys.exit(0 if ok_all else 1)
