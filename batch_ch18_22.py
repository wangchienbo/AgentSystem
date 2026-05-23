import requests, time, json

BASE = "http://localhost:80"
NOVEL_ID = "novel_20260519095419_30f0ac4e"
CHAPTERS_TO_WRITE = 5
TICK_DELAY = 10
CHAPTER_DELAY = 10

def dispatch(op, params=None):
    r = requests.post(f"{BASE}/api/task/dispatch", json={"app":"novel_studio","operation":op,"params":params or {}}, timeout=120)
    data = r.json()
    tid = data["task"]["task_id"]
    for _ in range(120):
        time.sleep(2)
        t = requests.get(f"{BASE}/api/task/{tid}", timeout=30).json().get("task", {})
        if t.get("status") == "done":
            return t.get("result")
        if t.get("status") == "failed":
            print(f"  FAILED: {t.get('error')}")
            return None
    return None

# 获取当前状态
state = dispatch("get_evolution_state")
if not state:
    print("无法获取演化状态")
    exit(1)

current_tick = state.get("evolution_state", state).get("current_tick", 0)
chapters = state.get("novel", {}).get("chapters", state.get("chapters", []))
current_ch = len(chapters)
print(f"当前: tick={current_tick}, 已有{current_ch}章, 续写{CHAPTERS_TO_WRITE}章")

for i in range(CHAPTERS_TO_WRITE):
    ch_num = current_ch + i + 1
    print(f"\n--- 第{ch_num}章 ---")
    
    # tick 1
    print(f"  Tick 1...")
    r1 = dispatch("tick")
    if r1:
        ev = r1.get("evolution_state", r1)
        print(f"  tick -> {ev.get('current_tick')}")
    time.sleep(TICK_DELAY)
    
    # tick 2
    print(f"  Tick 2...")
    r2 = dispatch("tick")
    if r2:
        ev = r2.get("evolution_state", r2)
        print(f"  tick -> {ev.get('current_tick')}")
    time.sleep(TICK_DELAY)
    
    # 写章节
    print(f"  写入第{ch_num}章...")
    chapter = dispatch("write_narrative_chapter")
    if chapter:
        ch = chapter.get("chapter", chapter)
        title = ch.get("title", "未知")
        wc = ch.get("word_count", 0)
        print(f"  ✅ {title} ({wc}字)")
    else:
        print(f"  ❌ 写入失败")
    time.sleep(CHAPTER_DELAY)

# 最终状态
print("\n=== 最终状态 ===")
final = dispatch("get_evolution_state")
if final:
    novel = final.get("novel", {})
    chapters = novel.get("chapters", final.get("chapters", []))
    total_words = sum(c.get("word_count", 0) for c in chapters)
    print(f"总章数: {len(chapters)}")
    print(f"总字数: {total_words}")
    print(f"最新章节: {chapters[-1].get('title') if chapters else '无'}")

# 导出 txt
print("\n=== 导出 TXT ===")
novel_data = dispatch("get_novel_state")
if novel_data:
    novel = novel_data.get("novel", novel_data)
    title = novel.get("title", "小说")
    chapters = novel.get("chapters", [])
    txt_lines = [f"《{title}》\n\n"]
    for ch in chapters:
        ch_title = ch.get("title", "")
        ch_content = ch.get("content", "")
        txt_lines.append(f"\n{'='*40}\n{ch_title}\n{'='*40}\n\n{ch_content}\n")
    
    output_path = f"/root/{title}.txt".replace(" ", "_")
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(txt_lines)
    import os
    size = os.path.getsize(output_path)
    print(f"✅ 已导出: {output_path} ({size} bytes, {len(chapters)}章)")
