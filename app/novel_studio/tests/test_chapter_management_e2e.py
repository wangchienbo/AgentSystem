#!/usr/bin/env python3
"""Test chapter management (edit/delete) in Novel Studio."""
import json, sys, time
from playwright.sync_api import sync_playwright

CHROME = "/home/ubuntu/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome"
BASE = "http://127.0.0.1:8765"
NOVEL_ID = "novel_20260523194534_44eee341"

results = []
def check(name, ok, detail=""):
    status = "✅" if ok else "❌"
    results.append((name, ok))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))

print("=" * 60)
print("📋 章节管理功能测试")
print("=" * 60)

# ─── Step 1: curl API tests ───
print("\n1️⃣  API 层测试")

# 1a: Create a chapter via chat/stream
import subprocess
print("\n  [1a] 生成新章节...")
r = subprocess.run(["curl", "-s", "--max-time", "120", "-X", "POST",
    BASE + "/api/novel/chat/stream",
    "-H", "Content-Type: application/json",
    "-d", json.dumps({"novel_id": NOVEL_ID, "message": "写第19章，标题：星空之门"})],
    capture_output=True, text=True)
lines = r.stdout.strip().split("\n")
chapter_info = None
for line in lines:
    if not line.strip(): continue
    d = json.loads(line)
    if d.get("done") and d.get("chapter"):
        chapter_info = d["chapter"]
check("生成章节 API 成功", chapter_info is not None)
if chapter_info:
    check(f"  标题正确: {chapter_info.get('title')}", chapter_info.get("title") == "星空之门")

# 1b: Get chapters to find the string ID
r = subprocess.run(["curl", "-s", "--max-time", "10", "-X", "POST",
    BASE + "/api/novel/get",
    "-H", "Content-Type: application/json",
    "-d", json.dumps({"novel_id": NOVEL_ID})],
    capture_output=True, text=True)
data = json.loads(r.stdout)
chapters = data.get("novel", {}).get("chapters", [])
check(f"小说有 {len(chapters)} 章", len(chapters) >= 19)

# Find chapter 19
ch19 = None
for ch in chapters:
    if ch.get("number") == 19:
        ch19 = ch
        break
check("找到第19章", ch19 is not None)

if ch19:
    ch19_id = ch19["id"]
    print(f"  Chapter 19 id={ch19_id}, title='{ch19.get('title')}'")

    # 1c: Update chapter title
    r = subprocess.run(["curl", "-s", "--max-time", "10", "-X", "POST",
        BASE + "/api/novel/chapter/update",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"novel_id": NOVEL_ID, "chapter_id": ch19_id, "title": "星空之门·改"})],
        capture_output=True, text=True)
    upd = json.loads(r.stdout)
    check("更新标题 API 成功", upd.get("success") is True)

    # Verify update persisted
    r = subprocess.run(["curl", "-s", "--max-time", "10", "-X", "POST",
        BASE + "/api/novel/get",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"novel_id": NOVEL_ID})],
        capture_output=True, text=True)
    data2 = json.loads(r.stdout)
    for ch in data2.get("novel", {}).get("chapters", []):
        if ch.get("number") == 19:
            check(f"  标题改为: {ch.get('title')}", ch.get("title") == "星空之门·改")
            break

    # 1d: Update chapter content
    r = subprocess.run(["curl", "-s", "--max-time", "10", "-X", "POST",
        BASE + "/api/novel/chapter/update",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"novel_id": NOVEL_ID, "chapter_id": ch19_id, "content": "这是修改后的第19章内容。" * 20})],
        capture_output=True, text=True)
    upd2 = json.loads(r.stdout)
    check("更新内容 API 成功", upd2.get("success") is True)

    # 1e: Delete chapter 19
    r = subprocess.run(["curl", "-s", "--max-time", "10", "-X", "POST",
        BASE + "/api/novel/chapter/delete",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"novel_id": NOVEL_ID, "chapter_number": 19})],
        capture_output=True, text=True)
    dlt = json.loads(r.stdout)
    check("删除章节 API 成功", dlt.get("success") is True)

    # Verify deletion
    r = subprocess.run(["curl", "-s", "--max-time", "10", "-X", "POST",
        BASE + "/api/novel/get",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"novel_id": NOVEL_ID})],
        capture_output=True, text=True)
    data3 = json.loads(r.stdout)
    chs = data3.get("novel", {}).get("chapters", [])
    deleted = all(ch.get("number") != 19 for ch in chs)
    check("第19章已删除", deleted)
    check(f"  剩余 {len(chs)} 章", len(chs) == 18)

# ─── Step 2: Playwright UI tests ───
print("\n2️⃣  UI 层测试（Playwright）")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    page.goto(f"{BASE}/studio", wait_until="networkidle")
    page.wait_for_timeout(1500)

    # Enter the novel
    card_count = page.locator(".card").count()
    check("小说列表已加载", card_count >= 1)
    page.locator(".card").first.click()
    page.wait_for_timeout(2000)

    # Check chapter list in sidebar
    chapters = page.locator(".tree-item.chapter")
    ch_count = chapters.count()
    check(f"章节树显示 {ch_count} 章", ch_count >= 1)

    # Click on a chapter to see detail
    page.locator(".tree-item.chapter").first.click()
    page.wait_for_timeout(500)
    detail_view = page.locator("#detail-view")
    dv = detail_view.is_visible()
    check("详情视图弹出", dv)

    # Check for edit button
    edit_btn = page.locator("button:has-text('编辑')")
    check("编辑按钮存在", edit_btn.is_visible() if dv else False)

    # Check for delete button
    delete_btn = page.locator("button:has-text('删除')")
    check("删除按钮存在", delete_btn.is_visible() if dv else False)

    # Click edit
    if edit_btn.is_visible():
        edit_btn.click()
        page.wait_for_timeout(500)
        edit_title = page.locator("#edit-title")
        edit_content = page.locator("#edit-content")
        check("编辑表单:标题输入框", edit_title.is_visible())
        check("编辑表单:内容编辑框", edit_content.is_visible())

        # Modify and save
        new_title = "第1章·编辑测试"
        edit_title.fill("")
        edit_title.type(new_title, delay=20)
        page.locator("button:has-text('保存')").click()
        page.wait_for_timeout(1500)

        # Check chapter was updated
        page.locator(".tree-item.chapter").first.click()
        page.wait_for_timeout(500)
        detail_body = page.locator("#detail-body").text_content() or ""
        check(f"章节标题已更新 ({new_title})", new_title in detail_body)

    # Console errors
    js_errors = [e for e in errors if "favicon" not in e.lower()]
    check("无 JS 异常", len(js_errors) == 0, f"{len(js_errors)} errors")

    browser.close()

# ─── Summary ───
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
if passed == total:
    print(f"🎉 全部 {total} 项章节管理测试通过！")
else:
    print(f"⚠️  {passed}/{total} 通过")
    for name, ok in results:
        if not ok:
            print(f"  ❌ {name}")
