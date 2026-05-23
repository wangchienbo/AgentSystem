#!/usr/bin/env python3
"""万历新明·穿越篇 — 限速批量续写（从第13章起，写5章）"""

import requests, json, time, os, sys

BASE = "http://localhost:80"
NID = "novel_20260519095419_30f0ac4e"
OUTPUT = os.path.expanduser("~/万历新明_穿越篇.txt")
RATE_LIMIT_DELAY = 10  # 每步操作间隔（秒）

def dispatch(app, op, params, timeout=180):
    for attempt in range(3):
        try:
            resp = requests.post(f"{BASE}/api/task/dispatch", json={
                "app": app, "operation": op, "params": params,
            }, timeout=timeout)
            j = resp.json()
            tid = j.get("task", {}).get("task_id", "")
            if tid:
                return tid
            print(f"  ⚠️ dispatch returned: {j}")
            return ""
        except Exception as e:
            print(f"  ⚠️ dispatch retry {attempt+1}: {e}")
            time.sleep(3)
    return ""

def wait(tid, sec=8):
    if not tid:
        return {}
    time.sleep(sec)
    for _ in range(12):
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

# 读取已有内容
existing = ""
if os.path.exists(OUTPUT):
    with open(OUTPUT, "r", encoding="utf-8") as f:
        existing = f.read()
    print(f"📖 已有内容: {len(existing)}字")

print("=" * 60)
print("《万历新明·穿越篇》— 限速批量续写")
print("=" * 60)

# ── 检查已有章节数 ──
try:
    r = requests.post(f"{BASE}/api/novel/get", json={"novel_id": NID}, timeout=10).json()
    stored = r.get("novel", {}).get("chapters", [])
    stored_chapters = len(stored)
    last_ch = stored[-1] if stored else {}
    print(f"📚 已存储: {stored_chapters} 章")
    print(f"   最新: #{last_ch.get('chapter_number','?')} 「{last_ch.get('title','?')}」({last_ch.get('word_count',0)}字)")
except Exception as e:
    stored_chapters = 0
    print(f"  ⚠️ 查询失败: {e}")

# ── 生成 5 章 ──
TARGET = stored_chapters + 5
start_ch = stored_chapters + 1

print(f"\n📝 目标: 从第 {start_ch} 章 → 第 {TARGET} 章（共 5 章）")
print(f"⏱  每步限速间隔: {RATE_LIMIT_DELAY}s\n")

for ch_num in range(start_ch, TARGET + 1):
    print(f"{'─'*50}")
    print(f"📝 第 {ch_num} 章")
    
    # tick × 6（推进剧情）
    for ti in range(6):
        start = time.time()
        tid = dispatch("novel_studio", "tick", {})
        t = wait(tid, 20)
        elapsed = time.time() - start
        r = t.get("result", {})
        actions = r.get("actions", [])
        tk = r.get("tick", "?")
        if actions:
            chars_acted = set(a.get('char','') for a in actions)
            print(f"  ⏱ t={tk} ({elapsed:.0f}s) → {' + '.join(chars_acted)}")
        else:
            print(f"  ⏱ t={tk} ({elapsed:.0f}s) → (空)")
        
        # 限速
        if ti < 5:
            time.sleep(RATE_LIMIT_DELAY)
    
    # 写章节
    print(f"  ✍️ 正在写第 {ch_num} 章...")
    tid = dispatch("novel_studio", "write_narrative_chapter", {})
    t = wait(tid, 45)
    r = t.get("result", {})
    
    if r.get("success"):
        content = r.get("content", "")
        ch_title = r.get("chapter_title", f"第{r.get('chapter_number')}章")
        wc = r.get("word_count", len(content))
        print(f"  ✅ 「{ch_title}」({wc}字)")
        
        # 追加到文件
        with open(OUTPUT, "a", encoding="utf-8") as f:
            f.write(f"\n\n{content}\n\n")
        print(f"  📄 已写入 {len(content)} 字到文件")
        
        # 保存状态
        tid = dispatch("novel_studio", "save_evolution_state", {"novel_id": NID})
        wait(tid, 2)
        print(f"  💾 演化状态已保存")
    else:
        err = r.get("error", "?")
        print(f"  ❌ 写章失败: {err}")
        # 重试一次
        print(f"  🔄 重试...")
        time.sleep(5)
        tid = dispatch("novel_studio", "write_narrative_chapter", {})
        t = wait(tid, 45)
        r = t.get("result", {})
        if r.get("success"):
            content = r.get("content", "")
            print(f"  ✅ 重试成功 ({r.get('word_count',0)}字)")
            with open(OUTPUT, "a", encoding="utf-8") as f:
                f.write(f"\n\n{content}\n\n")
        else:
            print(f"  ❌ 重试也失败了: {r.get('error','?')}")
    
    # 章间限速
    if ch_num < TARGET:
        print(f"  ⏳ 等待 {RATE_LIMIT_DELAY}s...")
        time.sleep(RATE_LIMIT_DELAY)

# ── 最终统计 ──
if os.path.exists(OUTPUT):
    with open(OUTPUT, "r", encoding="utf-8") as f:
        total = f.read()
    ch_count = total.count("第") // 2
    print(f"\n{'='*50}")
    print(f"📚 累计: ~{ch_count}章 / {len(total)}字")
    print(f"📄 {OUTPUT}")
    print(f"\n📋 最新 300 字:\n{total[-300:]}")
else:
    print(f"\n❌ 文件未生成")

# 最终保存
tid = dispatch("novel_studio", "save_evolution_state", {"novel_id": NID})
wait(tid, 2)
print(f"\n💾 最终状态已保存")
print("=" * 50)
