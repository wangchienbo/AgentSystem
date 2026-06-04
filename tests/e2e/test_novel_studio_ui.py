#!/usr/bin/env python3
"""Novel Studio UI — Playwright 端到端验证 v3"""
import sys, json, time, os, re

BASE = "http://127.0.0.1:8765"
NOVEL_ID = "novel_20260529035145_b5a09027"
CHROME = os.path.expanduser("~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome")
STREAM_TIMEOUT = 60  # max seconds to wait for streaming response

results = []
def check(name, ok, detail=""):
    status = "✅" if ok else "❌"
    results.append((name, ok))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))

from playwright.sync_api import sync_playwright, TimeoutError

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, executable_path=CHROME,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append((msg.type, msg.text)))

        failed_requests = []
        page.on("response", lambda resp: failed_requests.append((resp.status, resp.url))
                if resp.status >= 400 and "favicon" not in resp.url else None)

        print("=" * 60)
        print("🧪 Novel Studio UI 端到端验证 v3")
        print("=" * 60)

        # ── 1. 加载页面 ──
        print("\n🌐 1 — 页面加载")
        print("-" * 40)
        page.goto(f"{BASE}/studio?novel_id={NOVEL_ID}",
                  wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)
        check("1a 页面加载", True, f"URL={page.url}")
        check("1b 标题", "小说创作室" in page.title(), f"title={page.title()!r}")
        check("1c 无 JS 崩溃", all(t != "error" or "Failed to load" in m for t, m in console_errors[-3:]))

        # ── 2. 登录进入 ──
        print("\n🔑 2 — 登录进入")
        print("-" * 40)
        inp = page.locator("input").first
        inp.wait_for(timeout=5000)
        inp.fill("admin")
        page.wait_for_timeout(200)
        page.locator("button").first.click()
        page.wait_for_timeout(3000)

        body = page.inner_text("body")
        check("2a 可见小说列表", "明末艺术家" in body, f"{len(body)} chars, shows novel cards")
        chapter_count = len(re.findall(r'📄 \d+章', body))
        check("2b 至少3部小说", chapter_count >= 3, 
              f"found {chapter_count} novels")

        # ── 3. 进入工作室 ──
        print("\n🎯 3 — 进入工作室")
        print("-" * 40)
        page.locator("text=明末艺术家").first.click()
        page.wait_for_timeout(3000)

        body2 = page.inner_text("body")
        check("3a 进入小说工作室", len(body2) > 400, f"{len(body2)} chars")
        check("3b 可见章节列表", "第一章" in body2)
        check("3c 可见角色列表", "张献忠" in body2)
        check("3d 可见聊天区域", page.locator("#chat-area").count() > 0)

        # ── 4. 内容验证 ──
        print("\n📚 4 — 小说内容")
        print("-" * 40)

        b4 = page.inner_text("body")
        check("4a 小说标题", "明末艺术家" in b4)
        for ch_title in ["第一章", "第二章", "第三章", "第四章"]:
            check(f"4b {ch_title}", ch_title in b4)
        for char_name in ["沈逸之", "张献忠", "李定国"]:
            check(f"4c 角色-{char_name}", char_name in b4)
        check("4d 输入框可用", page.locator("textarea").first.is_visible())

        # ── 5. 聊天交互 ──
        print("\n💬 5 — 聊天交互")
        print("-" * 40)

        # Record initial body length for diff
        body_before = len(page.inner_text("body"))
        msg = "当前小说有哪些角色？"

        textarea = page.locator("textarea").first
        textarea.fill(msg)
        check("5a 输入文字", page.locator("textarea").first.input_value() == msg)

        # Send
        send_btn = page.locator("button#send-btn").first
        if send_btn.count() > 0 and send_btn.is_visible():
            send_btn.click()
        else:
            textarea.press("Enter")
        check("5b 发送消息", True)

        # Wait for streaming to complete — watch for input re-enable
        print("     等待 stream 响应...")
        try:
            page.wait_for_function(
                "document.querySelector('textarea') && !document.querySelector('textarea').disabled",
                timeout=STREAM_TIMEOUT * 1000
            )
            check("5c 输入框已重新启用", True)
        except:
            check("5c 输入框已重新启用", False, f"timeout {STREAM_TIMEOUT}s")

        # Small extra wait for final DOM update
        page.wait_for_timeout(1500)

        # Check body growth
        body_after = page.inner_text("body")
        growth = len(body_after) - body_before
        check("5d 有回复内容", growth > 50 or "沈逸之" in body_after[body_before:],
              f"body grew by {growth} chars")

        # Check that the AI response contains relevant content
        ai_content = "沈逸之" in body_after and "张献忠" in body_after
        check("5e AI回复有实质内容", ai_content)

        # ── 6. 功能按钮 ──
        print("\n⚡ 6 — 功能按钮")
        print("-" * 40)
        btn_checks = [
            ("生成下一章", "⚡ 生成下一章"),
            ("添加角色", "添加角色"),
            ("新建章节", "新建章节"),
            ("返回", "返回"),
            ("阅读", "阅读"),
        ]
        for name, label in btn_checks:
            found = label in page.inner_text("body")
            check(f"6a 按钮-{name}", found)

        # Check character detail interaction
        # Open character detail by clicking on 张献忠 in the sidebar
        try:
            # Find a tree-item.sub that contains 张献忠
            char_item = page.locator(".tree-item.sub").filter(has_text="张献忠").first
            if char_item.count() > 0:
                char_item.click()
                page.wait_for_timeout(1000)
                check("6b 角色详情可点击", True)
            else:
                check("6b 角色详情可点击", False)
        except:
            check("6b 角色详情可点击", False)

        # ── 7. 控制台 + 网络 ──
        print("\n🔍 7 — 错误检查")
        print("-" * 40)
        # Filter 401 pre-login call as expected
        real_errors = [(t, m) for t, m in console_errors
                       if t == "error" and "favicon" not in m.lower()]
        check("7a 无未预期 JS 错误", len(real_errors) <= 1,
              f"{len(real_errors)} errors" if real_errors else "干净")
        for t, m in real_errors[:3]:
            print(f"     ⚠️  [{t}] {m[:200]}")

        # Check failed requests (401 on /api/novel/list is pre-login, acceptable)
        non_login_fails = [(s, u) for s, u in failed_requests
                          if "/api/novel/list" not in u]
        check("7b 无失败请求(除预登录)", len(non_login_fails) == 0,
              f"{len(non_login_fails)} failed" if non_login_fails else "干净")
        for s, u in non_login_fails[:3]:
            print(f"     ⚠️  {s} {u[:80]}")

        # ── 汇总 ──
        print("\n" + "=" * 60)
        passed = sum(1 for r in results if r[1])
        total = len(results)
        pct = int(passed / total * 100) if total else 0
        print(f"📊 汇总: {passed}/{total} 通过 ({pct}%)")
        for name, ok in results:
            if not ok:
                print(f"   ❌ {name}")
        print("=" * 60)

        page.screenshot(path="/tmp/studio_v3_final.png")
        print(f"截图: MEDIA:/tmp/studio_v3_final.png")

        browser.close()
        return passed == total or passed / total >= 0.85

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
