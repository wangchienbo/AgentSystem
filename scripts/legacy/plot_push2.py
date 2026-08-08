#!/usr/bin/env python3
"""plot_push2.py — 继续推进：沈三进茶馆，金手指首次使用"""

import requests, json, time, os

BASE = "http://localhost:80"
NID = "novel_20260519095419_30f0ac4e"

def d(op, params, timeout=120):
    for _ in range(3):
        try:
            r = requests.post(f"{BASE}/api/task/dispatch", json={"app": "novel_studio", "operation": op, "params": params}, timeout=timeout)
            return r.json().get("task", {}).get("task_id", "")
        except: time.sleep(3)
    return ""

def w(tid, sec=8):
    if not tid: return {}
    time.sleep(sec)
    for _ in range(6):
        try:
            r = requests.get(f"{BASE}/api/task/{tid}", timeout=15)
            s = r.json().get("task", {}).get("status")
            if s and s != "running": return r.json().get("task", {})
        except: pass
        time.sleep(5)
    return {}

OUT = os.path.expanduser("~/万历新明_穿越篇.txt")

print("🚀 第7-9章：沈三入局，金手指初现")
print("=" * 50)

# ── 沈三进入茶馆（情景驱动）──
print("\n🚶 沈三进茶馆求救")
tid = d("place_character", {"char_name": "沈三", "scene_name": "顾家茶馆"})
w(tid, 2)
print("  ✅")

# ── 追踪者也到了附近 ──
print("\n🌩️ 追踪者逼近")
tid = d("add_world_event", {
    "title": "追踪者到茶馆外",
    "description": "两个穿短打的便衣在茶馆附近停下来，像是在找人，其中一个往茶馆窗口看了几眼",
    "event_type": "danger",
})
w(tid, 2)
print("  ✅")

# ── 送信的回后院找那包东西 ──
print("\n🌩️ 关键线索：那包东西")
tid = d("add_world_event", {
    "title": "沈墨找到包裹",
    "description": "沈墨在后院东厢的书版堆底层，发现了一个用油布包着的包裹，里头是一本账册的抄本和几封信。这正是那个死在狱中的书吏托人送来的东西。",
    "event_type": "mystery",
})
w(tid, 2)
print("  ✅ 关键物证出现")

# ── 连续演化 x12 ──
print(f"\n🎭 演化 x12（三线交汇）...")
for i in range(12):
    start = time.time()
    tid = d("tick", {})
    t = w(tid, 18)
    tk = t.get("result", {}).get("tick", "?")
    actions = t.get("result", {}).get("actions", [])
    if actions:
        chars = "+".join(set(a.get('char','') for a in actions))
        print(f"  t={tk} ({time.time()-start:.0f}s) → {chars}")
    else:
        print(f"  t={tk} — ∅")

# ── 写第7章 ──
print(f"\n✍️ 第7章...")
tid = d("write_narrative_chapter", {})
t = w(tid, 35)
r = t.get("result", {})
if r.get("success"):
    content = r.get("content", "")
    print(f"  ✅ ({r.get('word_count')}字)")
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(f"\n\n{content}\n\n")
    # 提取关键段落判断剧情是否推进
    print(f"  📄 已追加")
    # 看开头150字
    for l in content.strip().split('\n')[:6]:
        print(f"  {l[:120]}")

# 保存
tid = d("save_evolution_state", {"novel_id": NID})
w(tid, 2)
print(f"💾 Saved")

# ── 继续第8章 ──
print(f"\n✍️ 第8章（续）...")
for i in range(6):
    start = time.time()
    tid = d("tick", {})
    t = w(tid, 18)
    tk = t.get("result", {}).get("tick", "?")
    actions = t.get("result", {}).get("actions", [])
    if actions:
        chars = "+".join(set(a.get('char','') for a in actions))
        print(f"  t={tk} ({time.time()-start:.0f}s) → {chars}")

tid = d("write_narrative_chapter", {})
t = w(tid, 35)
r = t.get("result", {})
if r.get("success"):
    content = r.get("content", "")
    print(f"  ✅ 第8章 ({r.get('word_count')}字)")
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(f"\n\n{content}\n\n")

# ── 第9章 ──
print(f"\n✍️ 第9章...")
for i in range(6):
    start = time.time()
    tid = d("tick", {})
    t = w(tid, 18)
    tk = t.get("result", {}).get("tick", "?")
    actions = t.get("result", {}).get("actions", [])
    if actions:
        chars = "+".join(set(a.get('char','') for a in actions))
        print(f"  t={tk} ({time.time()-start:.0f}s) → {chars}")

tid = d("write_narrative_chapter", {})
t = w(tid, 35)
r = t.get("result", {})
if r.get("success"):
    content = r.get("content", "")
    print(f"  ✅ 第9章 ({r.get('word_count')}字)")
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(f"\n\n{content}\n\n")

# 最终统计
with open(OUT, "r", encoding="utf-8") as f:
    total = f.read()
print(f"\n{'='*50}")
print(f"📚 累计: ~9章 / {len(total)}字 / {OUT}")
tid = d("save_evolution_state", {"novel_id": NID})
w(tid, 2)
print(f"💾 最终状态已保存")
print(f"{'='*50}")
