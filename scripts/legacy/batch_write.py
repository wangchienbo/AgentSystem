#!/usr/bin/env python3
"""万历新明 — 批量生成脚本（自动续写）"""

import requests, json, time, os, sys

BASE = "http://localhost:80"
NID = "novel_20260519095419_30f0ac4e"

def dispatch(app, op, params, timeout=120):
    for attempt in range(3):
        try:
            resp = requests.post(f"{BASE}/api/task/dispatch", json={
                "app": app, "operation": op, "params": params,
            }, timeout=timeout)
            return resp.json().get("task", {}).get("task_id", "")
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
    return ""

def wait(tid, sec=8):
    if not tid:
        return {}
    time.sleep(sec)
    for _ in range(6):
        try:
            r = requests.get(f"{BASE}/api/task/{tid}", timeout=15)
            t = r.json().get("task", {})
            s = t.get("status")
            if s and s != "running":
                return t
        except:
            pass
        time.sleep(5)
    return {"status": "timeout"}

OUTPUT = os.path.expanduser("~/万历新明_穿越篇.txt")
# 读取已有内容确保不覆盖
existing = ""
if os.path.exists(OUTPUT):
    with open(OUTPUT, "r", encoding="utf-8") as f:
        existing = f.read()
    print(f"📖 已有内容: {len(existing)}字")

print("=" * 50)
print("《万历新明·穿越篇》— 批量续写")
print("=" * 50)

# ── 检查小说中的章节数 ──
try:
    r = requests.post(f"{BASE}/api/novel/get", json={"novel_id": NID}, timeout=10).json()
    stored_chapters = len(r.get("novel", {}).get("chapters", []))
except:
    stored_chapters = 0
print(f"📚 已存储章节: {stored_chapters}")

# ── 生成指定数量的章节 ──
TARGET_CHAPTERS = 5  # 先写5章
start_chapter = stored_chapters + 1
if start_chapter < 1:
    start_chapter = 1

print(f"\n从第 {start_chapter} 章开始，目标 {TARGET_CHAPTERS} 章")

for ch_num in range(start_chapter, TARGET_CHAPTERS + 1):
    print(f"\n{'─'*40}")
    print(f"📝 第{ch_num}章")
    
    # 每次写章前跑 6 个 tick（推进剧情）
    ticks_needed = 6
    for ti in range(ticks_needed):
        start = time.time()
        tid = dispatch("novel_studio", "tick", {})
        t = wait(tid, 20)
        elapsed = time.time() - start
        r = t.get("result", {})
        actions = r.get("actions", [])
        tk = r.get("tick", "?")
        if actions:
            # 只打印关键行动摘要
            chars_acted = set(a.get('char','') for a in actions)
            print(f"  ⏱ t={tk} ({elapsed:.0f}s) → {'+'.join(chars_acted)}")
        else:
            print(f"  ⏱ t={tk} — empty")
    
    # 写章节
    print(f"  ✍️ 正在写第{ch_num}章...")
    tid = dispatch("novel_studio", "write_narrative_chapter", {})
    t = wait(tid, 35)
    r = t.get("result", {})
    
    if r.get("success"):
        content = r.get("content", "")
        print(f"  ✅ 第{r.get('chapter_number')}章 ({r.get('word_count')}字)")
        
        # 追加到文件
        with open(OUTPUT, "a", encoding="utf-8") as f:
            f.write(f"\n\n{content}\n\n")
        
        print(f"  📄 已写入 {len(content)} 字")
        
        # 每章结束保存状态
        tid = dispatch("novel_studio", "save_evolution_state", {"novel_id": NID})
        wait(tid, 2)
        print(f"  💾 状态已保存 (tick #{r.get('tick_used','?')})")
    else:
        print(f"  ❌ 写章失败: {r.get('error','?')}")
        # 再试一次
        tid = dispatch("novel_studio", "write_narrative_chapter", {})
        t = wait(tid, 35)
        r = t.get("result", {})
        if r.get("success"):
            content = r.get("content", "")
            print(f"  ✅ 重试成功: {r.get('word_count')}字")
            with open(OUTPUT, "a", encoding="utf-8") as f:
                f.write(f"\n\n{content}\n\n")

# 最终统计
if os.path.exists(OUTPUT):
    with open(OUTPUT, "r", encoding="utf-8") as f:
        total = f.read()
    ch_count = total.count("第") // 2  # 粗略
    print(f"\n{'='*50}")
    print(f"📚 累计: ~{ch_count}章 / {len(total)}字")
    print(f"📄 {OUTPUT}")
    
    # 显示最后500字（当前进展）
    print(f"\n📋 最新段落:\n{total[-500:]}")
else:
    print(f"\n❌ 文件未生成")

# 保存最终状态
tid = dispatch("novel_studio", "save_evolution_state", {"novel_id": NID})
wait(tid, 2)
print(f"\n💾 最终状态已保存")
print("=" * 50)
