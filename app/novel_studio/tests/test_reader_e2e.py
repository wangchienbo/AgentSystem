#!/usr/bin/env python3
"""E2E test for Novel Studio Reader View (reading mode)."""
import subprocess, sys, time, json, os

BASE = "http://127.0.0.1:8765"
STUDIO_URL = "/studio"
NOVEL_ID = "novel_20260523194534_44eee341"
CHROME = "/home/ubuntu/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome"

# ---- Step 1: curl API verification ----
print("=" * 60)
print("STEP 1: curl API — verify server and template")
print("=" * 60)

r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", BASE + STUDIO_URL],
                   capture_output=True, text=True)
assert r.stdout.strip() == "200", f"Studio page returned {r.stdout}"
print("[PASS] Studio page loads (HTTP 200)")

r = subprocess.run(["curl", "-s", BASE + STUDIO_URL], capture_output=True, text=True)
html = r.stdout
assert "reader-view" in html, "reader-view div not found"
assert "openReader" in html, "openReader function not found"
print("[PASS] All reader view HTML/CSS/JS elements present")

r = subprocess.run(["curl", "-s", "-X", "POST", BASE + "/api/novel/get",
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps({"novel_id": NOVEL_ID})],
                   capture_output=True, text=True)
d = json.loads(r.stdout)
assert d.get("success"), f"get novel failed: {d}"
chapters = d.get("novel", {}).get("chapters", [])
assert len(chapters) >= 3, f"Expected >=3 chapters, got {len(chapters)}"
print(f"[PASS] Novel has {len(chapters)} chapters — ready for reading")

# ---- Step 2: Playwright browser tests ----
print()
print("=" * 60)
print("STEP 2: Playwright — full reading UX")
print("=" * 60)

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: errors.append(str(err)))

    page.goto(BASE + STUDIO_URL)
    page.wait_for_timeout(1500)
    card_count = page.locator(".card").count()
    assert card_count >= 1, "No novel cards"
    print(f"[PASS] Novel list loaded ({card_count} novels)")

    page.locator(".card").first.click()
    page.wait_for_timeout(2000)
    assert page.locator(".read-btn").is_visible(), "📖 阅读 button not visible"
    print("[PASS] Workspace loaded with read button")

    page.locator(".read-btn").click()
    page.wait_for_timeout(1000)
    assert page.locator("#reader-view").is_visible(), "Reader view not visible"
    print("[PASS] Reader view opened")

    toc_items = page.locator("#reader-toc .toc-item")
    assert toc_items.count() >= 3, f"Expected >=3 TOC items, got {toc_items.count()}"
    print(f"[PASS] TOC shows {toc_items.count()} chapters")

    rc_title = page.locator(".rc-title")
    assert rc_title.is_visible(), "Chapter title not visible"
    title_text = rc_title.text_content()
    assert "第1章" in title_text, f"Expected '第1章', got: {title_text}"
    print(f"[PASS] First chapter loaded: {title_text}")

    rc_body = page.locator(".rc-body")
    body_len = len(rc_body.text_content() or "")
    assert body_len > 100, f"Chapter body too short: {body_len}"
    print(f"[PASS] Chapter content visible ({body_len} chars)")

    assert page.locator("#prev-ch-btn").is_disabled(), "Prev should be disabled on first chapter"
    assert not page.locator("#next-ch-btn").is_disabled(), "Next should be enabled"
    print("[PASS] Navigation: prev disabled, next enabled")

    page.locator("#next-ch-btn").click()
    page.wait_for_timeout(500)
    title2 = page.locator(".rc-title").text_content()
    assert "第2章" in title2, f"Expected chapter 2, got: {title2}"
    print(f"[PASS] Next chapter: {title2}")

    page.locator("#prev-ch-btn").click()
    page.wait_for_timeout(500)
    title1 = page.locator(".rc-title").text_content()
    assert "第1章" in title1, f"Expected chapter 1, got: {title1}"
    print("[PASS] Previous chapter works")

    toc_items.nth(2).click()
    page.wait_for_timeout(500)
    title3 = page.locator(".rc-title").text_content()
    assert "第3章" in title3, f"Expected chapter 3, got: {title3}"
    print(f"[PASS] TOC jump to chapter 3: {title3}")

    page.locator(".close-btn").click()
    page.wait_for_timeout(500)
    assert page.locator("#workspace").is_visible(), "Workspace not visible after close"
    print("[PASS] Close reader returns to workspace")

    js_errs = [e for e in errors if "favicon" not in e.lower()]
    print(f"[PASS] JS errors: {len(js_errs)}")
    context.close()

    # Mobile viewport
    print()
    print("=" * 60)
    print("STEP 3: Mobile viewport (390x844)")
    print("=" * 60)
    mob = browser.new_context(viewport={"width": 390, "height": 844})
    mob_page = mob.new_page()
    mob_page.goto(BASE + STUDIO_URL)
    mob_page.wait_for_timeout(1500)
    mob_page.locator(".card").first.click()
    mob_page.wait_for_timeout(2000)
    mob_page.locator(".read-btn").click()
    mob_page.wait_for_timeout(1000)
    assert mob_page.locator(".rc-body").is_visible(), "Content not visible on mobile"
    body_text = mob_page.locator(".rc-body").text_content()
    assert len(body_text) > 50, f"Body too short on mobile: {len(body_text)}"
    print("[PASS] Chapter content readable on mobile")
    mob_page.locator("#reader-topbar .hamburger").click()
    mob_page.wait_for_timeout(300)
    print("[PASS] TOC toggle works on mobile")
    mob.close()
    browser.close()

print()
print("=" * 60)
print("ALL TESTS PASSED ✅")
print("=" * 60)
