#!/usr/bin/env python3
"""plot_push.py — 剧情推进器：打破僵局"""

import requests, json, time, os

BASE = "http://localhost:80"
NID = "novel_20260519095419_30f0ac4e"

def dispatch(app, op, params, timeout=120):
    for _ in range(3):
        try:
            r = requests.post(f"{BASE}/api/task/dispatch", json={"app": app, "operation": op, "params": params}, timeout=timeout)
            return r.json().get("task", {}).get("task_id", "")
        except Exception as e:
            time.sleep(3)
    return ""

def wait(tid, sec=8):
    if not tid: return {}
    time.sleep(sec)
    for _ in range(6):
        try:
            r = requests.get(f"{BASE}/api/task/{tid}", timeout=15)
            s = r.json().get("task", {}).get("status")
            if s and s != "running": return r.json().get("task", {})
        except: pass
        time.sleep(5)
    return {"status": "timeout"}

print("🚀 剧情推进：打破僵局")
print("=" * 50)

# 1. 叶思远移动到茶馆（主动出击）
print("\n🚶 叶思远 → 顾家茶馆（从隐藏到行动）")
tid = dispatch("novel_studio", "place_character", {"char_name": "叶思远", "scene_name": "顾家茶馆"})
wait(tid, 2)
print("  已移动 ✅")

# 沈墨留在后院继续守着
print("  沈墨留守后院 ✅")

# 2. 世界事件：顾娘子递来消息
print("\n🌩️ 事件：顾娘子透露线索")
tid = dispatch("novel_studio", "add_world_event", {
    "title": "织造局的账目",
    "description": "顾娘子在添茶时低声告诉叶思远：苏州织造局有一批被'漂没'的丝绸，经手的书吏半个月前死在牢里，死前曾托人往叶家送过一包东西。那包东西被原身收下了，这就是他被盯上的原因。",
    "event_type": "mystery",
})
wait(tid, 2)
print("  ✅ 线索已注入")

# 3. 新角色：神秘的书吏
print("\n👤 新角色：沈三（织造局书吏，知道内情的人）")
tid = dispatch("novel_studio", "add_character", {
    "novel_id": NID, "name": "沈三", "archetype": "配角",
    "personality": ["胆小", "精明", "滑头"],
    "background": "苏州织造局的小书吏，干了十几年，对局里的账目门儿清。他知道那批被'漂没'的丝绸是怎么回事，也知道经手的书吏是怎么死的。这几天他总觉得有人要灭他的口。",
    "goal": "活命，把烫手的证据甩出去",
    "speech_style": "声音小，语速快，习惯性左右张望",
})
wait(tid, 2)
print("  ✅ 沈三（知道内情的书吏）")
# 放他在府衙前街（他不敢进茶馆也不敢回织造局）
tid = dispatch("novel_studio", "place_character", {"char_name": "沈三", "scene_name": "苏州府衙门前街"})
wait(tid, 2)
print("  沈三在府衙前街徘徊 ✅")

# 4. 新事件：沈三的求救
print("\n🌩️ 事件：有人跟踪沈三")
tid = dispatch("novel_studio", "add_world_event", {
    "title": "灭口",
    "description": "两个穿便装的人从织造局方向出来，沿街打听一个姓沈的书吏。沈三听见风声，正在找机会脱身。",
    "event_type": "danger",
})
wait(tid, 2)
print("  ✅ 有人在追沈三")

# 5. 演化 x8（让剧情发酵）
print(f"\n🎭 演化 x8（推动剧情）...")
for i in range(8):
    start = time.time()
    tid = dispatch("novel_studio", "tick", {})
    t = wait(tid, 18)
    elapsed = time.time() - start
    tk = t.get("result", {}).get("tick", "?")
    actions = t.get("result", {}).get("actions", [])
    if actions:
        chars_acted = set(a.get('char','') for a in actions)
        print(f"  t={tk} ({elapsed:.0f}s) → {'+'.join(chars_acted)}")

# 6. 写第6章
print(f"\n✍️ 写第6章...")
tid = dispatch("novel_studio", "write_narrative_chapter", {})
t = wait(tid, 35)
r = t.get("result", {})
if r.get("success"):
    content = r.get("content", "")
    print(f"  ✅ 第{r.get('chapter_number')}章 ({r.get('word_count')}字)")
    outdir = os.path.expanduser("~/万历新明_穿越篇.txt")
    with open(outdir, "a", encoding="utf-8") as f:
        f.write(f"\n\n{content}\n\n")
    print(f"  📄 已追加")
    print(f"\n{'='*60}")
    # 新章节内容摘要（首尾各300字）
    lines = content.strip().split('\n')
    print("开头:")
    for l in lines[:8]:
        print(l[:100])
    print(f"\n... (共计{len(content)}字)")
    print("\n结尾:")
    for l in lines[-5:]:
        print(l[:100])

# 保存
tid = dispatch("novel_studio", "save_evolution_state", {"novel_id": NID})
wait(tid, 2)
print(f"\n💾 已保存")
print("=" * 50)
