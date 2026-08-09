#!/usr/bin/env python3
"""OS 工作台 Playwright 端到端回归 — 新时代 AI 操作系统工作台闭环验证

覆盖：工作台加载 / App 生命周期按钮 / Skill 详情展开 / 治理概览 / 自由设计闭环 / OS API。
用法：
    python tests/e2e/test_os_workbench_e2e.py          # 跑全量
    python tests/e2e/test_os_workbench_e2e.py --api     # 只跑 OS API 层（不经浏览器）
需先启动服务器：python -m uvicorn app.system.http_test_server:app --port 8765
"""
import sys, json, time, os

BASE = "http://127.0.0.1:8765"
CHROME = os.path.expanduser("~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome")
API_ONLY = "--api" in sys.argv

results = []
def check(name, ok, detail=""):
    status = "✅" if ok else "❌"
    results.append((name, ok))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))


def api(path, method="GET", body=None, timeout=120):
    """直接调用 OS API（用 urllib，避免浏览器依赖）。"""
    import urllib.request
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def verify_os_api():
    """OS API 层回归：overview / governance / skills 详情一致性。"""
    print("\n🔌 OS API 层")
    print("-" * 40)

    ov = api("/api/os/overview")
    check("A1 overview 返回", ov.get("success") is True)
    apps = ov.get("apps", [])
    skills = ov.get("skills", [])
    check("A2 有 App 目录", len(apps) >= 1, f"{len(apps)} apps")
    check("A3 有 Skill 库", len(skills) >= 1, f"{len(skills)} skills")

    # 关键：overview 列出的每个 skill，详情必须可查（数据源一致性）
    fail_skills = []
    for s in skills:
        d = api(f"/api/os/skills/{s['skill_id']}")
        if d.get("status") != "ok":
            fail_skills.append(s["skill_id"])
    check("A4 所有 skill 详情可查", not fail_skills,
          f"{len(skills) - len(fail_skills)}/{len(skills)} 可查" if fail_skills else f"{len(skills)}/{len(skills)}")

    gov = api("/api/os/governance")
    check("A5 governance 返回", gov.get("status") == "ok")
    check("A6 治理有审计计数", isinstance(gov.get("audit", {}).get("count"), int))


def verify_workbench(page):
    """浏览器工作台闭环回归。"""
    print("\n🖥️  工作台 UI")
    print("-" * 40)

    page.goto(f"{BASE}/workbench", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(1200)
    check("B1 页面加载", "AI 操作系统" in page.title(), f"title={page.title()!r}")
    check("B2 App 渲染", page.locator(".app-card").count() >= 1)
    check("B3 Skill 渲染", page.locator(".skill").count() >= 1)
    check("B4 治理区块", page.locator("#govPanel").is_visible())

    # Skill 详情展开
    page.locator(".skill").first.click()
    page.wait_for_timeout(700)
    detail = page.locator(".skill-detail").first.inner_text()
    check("B5 Skill 详情展开", "适配器" in detail and "能力画像" in detail)

    # App 生命周期按钮
    has_lifecycle = page.locator("text=⏹ 停止").count() >= 1 or page.locator("text=▶ 启动").count() >= 1
    check("B6 生命周期按钮", has_lifecycle)
    check("B7 删除按钮", page.locator("text=🗑 删除").count() >= 1)

    # 治理数据渲染（有审计记录）
    gov_actions = page.locator("#govActions").inner_text()
    check("B8 治理操作统计", len(gov_actions.strip()) > 0, f"actions={gov_actions[:40]}")


def main():
    print("=" * 60)
    print("🧪 OS 工作台端到端回归")
    print("=" * 60)

    verify_os_api()

    if not API_ONLY:
        from playwright.sync_api import sync_playwright
        console_errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, executable_path=CHROME,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.on("console", lambda m: console_errors.append((m.type, m.text))
                    if m.type == "error" else None)
            verify_workbench(page)
            browser.close()

        js_errors = [t for t, _ in console_errors if "favicon" not in _]
        check("B9 无 JS 错误", len(js_errors) == 0,
              f"{len(js_errors)} errors" if js_errors else "干净")

    # 汇总
    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r[1])
    total = len(results)
    pct = int(passed / total * 100) if total else 0
    print(f"📊 汇总: {passed}/{total} 通过 ({pct}%)")
    for name, ok in results:
        if not ok:
            print(f"   ❌ {name}")
    print("=" * 60)
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
