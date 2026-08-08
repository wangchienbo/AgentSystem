#!/usr/bin/env python3
"""万历新明 — 穿越小说自动生成（修复版）"""

import requests, json, time, os

BASE = "http://localhost:80"

def dispatch(app, op, params, timeout=120):
    for attempt in range(3):
        try:
            resp = requests.post(f"{BASE}/api/task/dispatch", json={
                "app": app, "operation": op, "params": params,
            }, timeout=timeout)
            return resp.json().get("task", {}).get("task_id", "")
        except Exception as e:
            print(f"  retry {attempt+1}: {e}")
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

print("=" * 50)
print("《万历新明·穿越篇》")
print("=" * 50)

# 全新小说
tid = dispatch("novel_studio", "create_novel", {"title": "万历新明·穿越篇", "genre": "历史穿越"})
t = wait(tid, 3)
nid = t.get("result", {}).get("novel_id", "")
print(f"\n📖 小说: {nid}")

# 世界观
print("\n🏔️ 万历四十五年·苏州")
tid = dispatch("novel_studio", "create_world", {
    "novel_id": nid, "name": "万历四十五年·苏州",
    "overview": "万历四十五年（公元1617年），万历皇帝已近三十年不上朝，朝政荒废，党争愈烈。江南苏州府表面繁华依旧，丝绸机杼声不绝，书坊刻书遍地，但暗流涌动。东厂与锦衣卫的耳目遍布街巷。一个穿越而来的现代灵魂，正困在这具书商之子的身躯里，试图在一场他尚未看清的棋局中活下来。",
    "rules": [
        "万历皇帝多年不上朝，朝政由内阁与司礼监运作",
        "东林党与浙党、楚党斗争激烈，江南是东林根基",
        "苏州织造局直属内廷，与地方官府有利益纠葛",
        "东厂在苏州有暗桩，专查民间议论朝政者",
        "今年苏州米价已涨三倍，饥民开始在城外聚集",
    ],
})
wait(tid, 2)
print("  ✅")

# 场景
print("\n🏚️ 场景...")
for s in [
    ("叶家书铺后院", "苏州城东青石巷内的一进小院。正屋三间，东厢堆着书版和纸张，西厢是卧房。天井里种着一棵老槐树，树下有口青石井。", ["远处市声", "风吹槐树叶"], ["旧书墨香", "井水的凉气"], "表面的宁静下藏着不安"),
    ("顾家茶馆", "街角的二层木楼，楼下散座，楼上雅间。窗临大街，能看见县衙方向和来往行人。", ["茶壶沸水声", "茶客低声交谈"], ["茶香", "糕点甜味"], "龙蛇混杂"),
    ("苏州府衙门前街", "青石板路面，两侧铺面鳞次栉比。府衙门口蹲着两只石狮子，台阶上常有候着的闲人。", ["脚步声", "叫卖声", "衙役呵斥声"], ["尘土", "官署熏香气"], "表面秩序，暗流涌动"),
]:
    tid = dispatch("novel_studio", "add_scene", {
        "novel_id": nid, "name": s[0], "description": s[1],
        "sounds": s[2], "smells": s[3], "atmosphere": s[4],
    })
    wait(tid, 2)
    print(f"  ✅ {s[0]}")

# ══════ 角色（含金手指） ══════
print("\n👤 角色...")

# 主角：穿越者，金手指：万象通明
tid = dispatch("novel_studio", "add_character", {
    "novel_id": nid, "name": "叶思远", "archetype": "主角",
    "personality": ["敏锐", "内敛", "适应力强"],
    "background": "现代历史系研究生，专注明史。在一次古籍拍卖会上触碰了一卷来历不明的万历年间手稿后昏迷，醒来发现自己附身在万历四十五年苏州一个同名同姓的书商之子身上。原身正在暗中调查苏州织造局的私账，已经被人盯上。他继承了原身的记忆碎片，但不完整。",
    "goal": "活下去，弄清楚自己为什么会被带到这个时代",
    "speech_style": "潜意识带现代用语痕迹，开口时努力模仿明代口吻，思考时完全现代思维",
    "attributes": {"intelligence": 16, "wisdom": 14, "charisma": 12},
    "special_ability": "万象通明——当他集中精神时，能'看见'事物之间隐藏的关联和本质：一个人的谎言会在他眼中呈现为模糊的杂音，隐藏的敌意会像阴影一样浮现在对方周围，复杂系统的运作逻辑会像图谱一样在脑中展开。缺点是极其消耗精神，连续使用不超过一炷香的时间（约5分钟），之后需要恢复。",
})
t = wait(tid, 2)
print(f"  ✅ 叶思远 — 穿越者【金手指：万象通明】")

# 书童
tid = dispatch("novel_studio", "add_character", {
    "novel_id": nid, "name": "沈墨", "archetype": "伙伴",
    "personality": ["忠诚", "谨慎", "细心"],
    "background": "叶家的书童，从小跟着少爷长大，识得几个字。前几日少爷出门回来后像变了个人，他察觉到了异样但没有声张。他知道少爷最近在查苏州织造局的私账，不敢多问，只默默替少爷挡着外面的耳目。",
    "goal": "保护少爷，守住叶家",
    "speech_style": "恭敬但带着亲近，有时候会忍不住说真话",
})
t = wait(tid, 2)
print(f"  ✅ 沈墨（书童）")

# 茶馆老板娘
tid = dispatch("novel_studio", "add_character", {
    "novel_id": nid, "name": "顾娘子", "archetype": "配角",
    "personality": ["精明", "圆滑", "不动声色"],
    "background": "苏州府衙斜对面的茶馆老板娘，三十出头，寡居。表面上是本分生意人，实际上各路消息都从她这张桌上过。她认识叶家少爷，也知道他在查什么，但还没决定站哪边。",
    "goal": "在各方势力之间保全自己",
    "speech_style": "话里有话，滴水不漏，带着茶香的笑意",
})
t = wait(tid, 2)
print(f"  ✅ 顾娘子（茶馆老板娘）")

# 势力
print("\n🔗 势力...")
for cmd in [
    ("set_faction", {"name": "叶思远", "faction_name": "叶家书铺", "rank": "少东家"}),
    ("set_faction", {"name": "沈墨", "faction_name": "叶家书铺", "rank": "书童"}),
    ("set_faction", {"name": "顾娘子", "faction_name": "中立", "rank": "茶馆老板娘"}),
]:
    tid = dispatch("novel_studio", cmd[0], {**cmd[1], "novel_id": nid})
    wait(tid, 2)
print("  ✅")

# ═══════ 演化 ═══════

print("\n🔄 初始化演化...")
tid = dispatch("novel_studio", "init_evolution", {"novel_id": nid, "resume": False})
t = wait(tid, 3)
r = t.get("result", {})
print(f"  {r.get('characters')}角色, {r.get('scenes')}场景")

# 放人
print("\n🚶 角色入场景...")
tid = dispatch("novel_studio", "place_character", {"char_name": "叶思远", "scene_name": "叶家书铺后院"})
wait(tid, 2)
tid = dispatch("novel_studio", "place_character", {"char_name": "沈墨", "scene_name": "叶家书铺后院"})
wait(tid, 2)
tid = dispatch("novel_studio", "place_character", {"char_name": "顾娘子", "scene_name": "顾家茶馆"})
wait(tid, 2)
print("  叶思远+沈墨在后院，顾娘在茶馆 ✅")

# 世界事件
print("\n🌩️ 事件：公差搜捕...")
tid = dispatch("novel_studio", "add_world_event", {
    "title": "衙役搜捕",
    "description": "两名公差从府衙方向拐进青石巷，正在挨户盘问，像是在找一个姓叶的书商之子",
    "event_type": "danger",
})
wait(tid, 2)
print("  ✅ 衙役已到巷口")

# 演化 x6
print(f"\n🎭 世界演化 x6...")
for i in range(6):
    start = time.time()
    tid = dispatch("novel_studio", "tick", {})
    t = wait(tid, 18)
    elapsed = time.time() - start
    r = t.get("result", {})
    actions = r.get("actions", [])
    tk = r.get("tick", "?")
    if not actions:
        print(f"  t={tk} — timeout")
        continue
    print(f"  t={tk} ({elapsed:.0f}s):")
    for a in actions:
        line = f"    {a.get('char')}: {a.get('action','')[:60]}"
        dlg = a.get("dialogue", "")
        if dlg:
            line += f'「{dlg[:55]}」'
        perc = a.get("perception", "")
        if perc and len(perc) < 60:
            line += f'  👁️{perc}'
        print(line)

# 生成章节
print(f"\n✍️ 生成第一章...")
tid = dispatch("novel_studio", "write_narrative_chapter", {})
t = wait(tid, 30)
r = t.get("result", {})
if r.get("success"):
    content = r.get("content", "")
    print(f"  ✅ 第{r.get('chapter_number')}章 ({r.get('word_count')}字)")
    outdir = os.path.expanduser("~/万历新明_穿越篇.txt")
    with open(outdir, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  📄 {outdir}")
    print(f"\n{'='*60}")
    print(content[:1800])
    print(f"\n{'='*60}")
    # 剩余部分
    if len(content) > 1800:
        print(f"\n... (剩余 {len(content)-1800} 字)")
else:
    print(f"  ❌ {r.get('error','?')}")

# 保存
tid = dispatch("novel_studio", "save_evolution_state", {"novel_id": nid})
wait(tid, 2)
print(f"\n💾 已保存")
print(f"\n{'='*50}")
print("✅ 完成")
