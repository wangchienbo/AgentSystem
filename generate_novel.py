#!/usr/bin/env python3
"""明末·风起 — 全自动生成"""

import requests, json, time, os, sys

BASE = "http://localhost:80"

def dispatch(app, op, params, timeout=120):
    resp = requests.post(f"{BASE}/api/task/dispatch", json={
        "app": app, "operation": op, "params": params,
    }, timeout=timeout)
    return resp.json().get("task", {}).get("task_id", "")

def wait(tid, sec=6):
    if not tid:
        return {}
    time.sleep(sec)
    for _ in range(6):
        try:
            r = requests.get(f"{BASE}/api/task/{tid}", timeout=10)
            if r.status_code != 200:
                return {}
            t = r.json().get("task", {})
            if t.get("status") != "running":
                return t
        except:
            return {}
        time.sleep(5)
    return {"status": "timeout"}

# ══════════ 小说设定 ══════════

print("=" * 60)
print("《明末·风起》— 崇祯十三年，陕西")
print("=" * 60)

tid = dispatch("novel_studio", "create_novel", {"title": "明末·风起", "genre": "历史"})
t = wait(tid, 3)
nid = t.get("result", {}).get("novel_id", "")
print(f"\n📖 小说: {nid}")

# 世界观
print("\n🏔️ 世界观...")
tid = dispatch("novel_studio", "create_world", {
    "novel_id": nid, "name": "崇祯十三年·陕西",
    "overview": (
        "崇祯十三年，陕西连年大旱，赤地千里，百姓易子而食。"
        "朝廷加征辽饷、剿饷、练饷，三饷并征，民不堪命。"
        "各地流民揭竿而起，李自成、张献忠等部辗转秦晋豫楚。"
        "官府镇压无力，地方团练与流寇交错，世道已乱。"
    ),
    "rules": [
        "崇祯十三年，陕西大旱，颗粒无收",
        "官府三饷并征，交不出粮就下狱",
        "各地流民起义，驿道已不安全",
        "地方团练保甲自守，对外人格外警惕",
        "朝廷公文仍在一道道往下发，但已没人当真执行",
    ],
})
wait(tid, 2)
print("  ✅")

# 场景
print("\n🏚️ 场景...")
scenes = [
    ("荒村破庙", (
        "村口的山神庙，屋顶塌了一半，只剩正殿还能避风。"
        "神像断了手臂，供桌被劈了当柴烧，墙上有火烧过的痕迹。"
        "地上铺着干草，角落里堆着半袋发霉的杂粮。"
    ), ["风穿过破窗的呼啸", "野狗远处吠叫"], ["尘土", "霉味", "烟火气"], "破败萧瑟"),
    ("官道驿站", (
        "驿道旁的三间土房，门前旗杆上挂着褪色的驿旗。"
        "墙皮剥落，窗纸破了大半。屋里只有一张破桌、两条长凳。"
        "灶台冷了很久，水缸已经见底。"
    ), ["风声", "远处隐约的马蹄声"], ["干草", "旧木"], "荒凉冷清"),
    ("河滩渡口", (
        "干涸的河床，只剩中间一线细流。两岸是龟裂的泥土，"
        "搁浅着一艘破旧的渡船。柳树枯了大半，枝条在风里乱晃。"
    ), ["流水声", "风吹枯柳"], ["干涸的泥土", "枯草"], "荒芜绝望"),
]

for sname, sdesc, sounds, smells, atmos in scenes:
    tid = dispatch("novel_studio", "add_scene", {
        "novel_id": nid, "name": sname, "description": sdesc,
        "sounds": sounds, "smells": smells, "atmosphere": atmos,
    })
    wait(tid, 2)
    print(f"  ✅ {sname}")

# 角色
print("\n👤 角色（含自动属性分配）...")

# 陈大 — 被逼反的农民
tid = dispatch("novel_studio", "add_character", {
    "novel_id": nid, "name": "陈大", "archetype": "主角",
    "personality": ["隐忍", "倔强", "重情义"],
    "background": (
        "陕西延安府农户，祖辈三代佃农。崇祯十年旱灾，颗粒无收，"
        "地主逼租，官府催粮，交不出来被锁拿游街。妻子病饿而死，"
        "老母在逃荒路上咽了气。他一把火烧了地主的粮仓，逃了出来。"
    ),
    "goal": "活下去，找一条穷人的活路",
    "speech_style": "话不多，陕西口音，急了才开口",
})
t = wait(tid, 2)
print(f"  ✅ 陈大（主角）")

# 周世亮 — 县衙捕头
tid = dispatch("novel_studio", "add_character", {
    "novel_id": nid, "name": "周世亮", "archetype": "对立角色",
    "personality": ["精明", "冷酷", "忠于职守"],
    "background": (
        "延安府捕头，干了十五年公差。早年也是个热血汉子，"
        "见多了乱世里的人命如草，变得铁石心肠。"
        "上司催得紧，要他把逃犯和流贼缉拿归案。"
        "他不管谁对谁错，只认王法。"
    ),
    "goal": "缉拿要犯，维持地方秩序",
    "speech_style": "官腔，冷，带几分不耐烦",
})
t = wait(tid, 2)
print(f"  ✅ 周世亮（对立角色）")

# 柳娘 — 逃难女医
tid = dispatch("novel_studio", "add_character", {
    "novel_id": nid, "name": "柳娘", "archetype": "女主角",
    "personality": ["坚韧", "敏锐", "寡言"],
    "background": (
        "祖传医术，父亲是乡间郎中。乱军过境时村子被烧，"
        "父亲被杀，她背着药箱逃了出来。一路上靠给人看病换口吃的。"
        "见过太多生死，知道什么该问什么不该问。"
    ),
    "goal": "活下去，找到安身之地",
    "speech_style": "平和，克制，偶尔带医者的冷静",
})
t = wait(tid, 2)
print(f"  ✅ 柳娘（女主角）")

# 势力（社会身份）
print("\n🔗 势力...")
for cmd in [
    ("set_faction", {"name": "陈大", "faction_name": "流民", "rank": "逃难者"}),
    ("set_faction", {"name": "周世亮", "faction_name": "官府", "rank": "捕头"}),
    ("set_faction", {"name": "柳娘", "faction_name": "流民", "rank": "医者"}),
]:
    tid = dispatch("novel_studio", cmd[0], {**cmd[1], "novel_id": nid})
    wait(tid, 2)
print("  ✅ 势力已设")

# ══════════ 演化 ══════════

print("\n🔄 初始化演化...")
tid = dispatch("novel_studio", "init_evolution", {"novel_id": nid, "resume": False})
t = wait(tid, 3)
r = t.get("result", {})
print(f"  {r.get('characters')}角色, {r.get('scenes')}场景")

# 放角色——三个人在破庙相遇（命运交叉点）
print("\n🚶 角色入场景...")
for p in [("陈大", "荒村破庙"), ("周世亮", "荒村破庙"), ("柳娘", "荒村破庙")]:
    tid = dispatch("novel_studio", "place_character", {"char_name": p[0], "scene_name": p[1]})
    wait(tid, 2)
print("  三人同入破庙 ✅")

# 世界事件：远处传来动静
print("\n🌩️ 世界事件注入...")
tid = dispatch("novel_studio", "add_world_event", {
    "title": "远处火光",
    "description": "东南方向的山脚下腾起一股黑烟，隐约有火光，像是又有村子被烧了",
    "event_type": "war",
})
wait(tid, 2)
print("  ✅")

# 演化
print(f"\n🎭 世界演化 x6...")
for i in range(6):
    start = time.time()
    tid = dispatch("novel_studio", "tick", {})
    t = wait(tid, 15)
    elapsed = time.time() - start
    r = t.get("result", {})
    actions = r.get("actions", [])
    if not actions:
        print(f"  t=? — timeout")
        continue
    print(f"  t={r.get('tick','?')} ({elapsed:.0f}s):")
    for a in actions:
        line = f"    {a.get('char')}: {a.get('action','')[:55]}"
        if a.get("dialogue"):
            line += f'「{a["dialogue"][:55]}」'
        print(line)

# 生成章节
print(f"\n✍️ 生成章节...")
tid = dispatch("novel_studio", "write_narrative_chapter", {})
t = wait(tid, 30)
r = t.get("result", {})
if r.get("success"):
    content = r.get("content", "")
    print(f"  ✅ 第{r.get('chapter_number')}章 ({r.get('word_count')}字)")
    
    outdir = os.path.expanduser("~/明末风起.txt")
    with open(outdir, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  📄 {outdir}")
    print(f"\n{'='*60}")
    print(content[:1800])
    print(f"\n{'='*60}")
else:
    print(f"  ❌ {r.get('error','?')}")

# 保存
tid = dispatch("novel_studio", "save_evolution_state", {"novel_id": nid})
t = wait(tid, 2)
print(f"\n💾 已保存")

# 日志
tid = dispatch("novel_studio", "export_evolution_log", {})
t = wait(tid, 2)
log = t.get("result", {}).get("log", "")
print(f"\n📋 演化日志:\n{log}")

print(f"\n{'='*60}")
print("✅ 完成")
print(f"{'='*60}")
