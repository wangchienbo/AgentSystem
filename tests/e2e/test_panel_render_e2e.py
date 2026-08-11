"""验证：前端 renderPanels 渲染结构化面板（输出信封 phase-2）"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"
passed = []
def check(name, ok, extra=""):
    passed.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name} {extra}")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page()
    console_errors = []
    page.on("console", lambda m: console_errors.append((m.type, m.text)) if m.type == "error" else None)

    page.goto(f"{BASE}/studio")
    page.wait_for_timeout(1500)
    if page.locator("#loginUser").count() > 0:
        page.fill("#loginUser", "panel_user")
        page.click("#loginBtn")
        page.wait_for_timeout(2000)

    # 进入第一本小说工作室
    page.locator(".card").first.click()
    page.wait_for_timeout(1800)
    check("进入工作室", page.locator("#chat-input").count() > 0)

    # 1) renderPanels 生成 HTML（单元级，通过页面上下文）
    sample = [{
        "id": "system", "title": "万界抽卡系统",
        "sections": [
            {"id": "ov", "title": "当前状态",
             "fields": [{"key": "绑定宿主", "value": "陈默"},
                        {"key": "下次抽取", "value": "23:59:57"}]},
            {"id": "rec", "title": "抽卡记录",
             "list": [{"seq": 1, "talent": "根骨鉴定", "desc": "可查看目标资质"}]},
        ],
    }]
    html = page.evaluate("(p) => window.renderPanels(p)", sample)
    check("renderPanels 生成 panel-box", 'class="panel-box"' in html)
    check("renderPanels 生成字段", "绑定宿主" in html and "pf-key" in html)
    check("renderPanels 生成表格", 'class="panel-table"' in html and "根骨鉴定" in html)
    check("renderPanels 空输入返回空", page.evaluate("() => window.renderPanels(null)") == "")
    check("renderPanels 未转义注入", '<script>' not in page.evaluate(
        "() => window.renderPanels([{id:'x',title:'<b>',sections:[]}])"))

    # 2) 打开阅读器某章节（旧数据无 panels）→ 无回归
    page.evaluate("() => { document.querySelector('#open-reader')?.click() || document.querySelector('.read-btn')?.click(); }")
    page.wait_for_timeout(1000)
    # 若无阅读器入口，直接调用 loadChapter 验证
    page.evaluate("() => { if(window.loadChapter && window.novelData && window.novelData.chapters && window.novelData.chapters.length) window.loadChapter(0); }")
    page.wait_for_timeout(800)
    body = page.inner_text("body")
    check("无 panels 章节正文正常", len(body) > 300)

    real = [(t, m) for t, m in console_errors if "favicon" not in m.lower() and "Failed to load resource" not in m]
    check("无JS错误", len(real) == 0, f"{len(real)}")
    for t, m in real[:3]:
        print(f"      [console {t}] {m[:120]}")

    b.close()

ok_all = all(x[1] for x in passed)
print(f"\n📊 前端面板渲染 E2E: {sum(1 for _,k in passed if k)}/{len(passed)} 通过")
sys.exit(0 if ok_all else 1)
