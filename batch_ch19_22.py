import requests, time, json

BASE = "http://localhost:80"
NOVEL_ID = "novel_20260519095419_30f0ac4e"
CHAPTERS_TO_WRITE = 4
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

def get_chapter_count():
    r = requests.post(f"{BASE}/api/novel/get", json={"novel_id": NOVEL_ID}, timeout=30)
    return len(r.json().get("novel", {}).get("chapters", []))

current_ch = get_chapter_count()
print(f"当前已有 {current_ch} 章，续写 {CHAPTERS_TO_WRITE} 章")

for i in range(CHAPTERS_TO_WRITE):
    ch_num = current_ch + i + 1
    print(f"\n--- 第{ch_num}章 ---")
    
    for tick_i in range(2):
        print(f"  Tick {tick_i+1}...")
        dispatch("tick")
        time.sleep(TICK_DELAY)
    
    print(f"  写入第{ch_num}章...")
    chapter = dispatch("write_narrative_chapter")
    if chapter:
        ch = chapter.get("chapter", chapter)
        title = ch.get("title", "未知")
        wc = ch.get("word_count", 0)
        print(f"  ✅ {title} ({wc}字)")
    else:
        # 看看章节有没有增加
        new_count = get_chapter_count()
        if new_count > current_ch + i:
            print(f"  ✅ 章节数从 {current_ch+i} 增加到 {new_count}")
        else:
            print(f"  ❌ 写入失败，章节数未变: {new_count}")
    time.sleep(CHAPTER_DELAY)

# 最终统计
final_count = get_chapter_count()
r = requests.post(f"{BASE}/api/novel/get", json={"novel_id": NOVEL_ID}, timeout=30)
chapters = r.json().get("novel", {}).get("chapters", [])
total_words = sum(c.get("word_count", 0) for c in chapters)
print(f"\n=== 最终: {final_count}章, {total_words}字 ===")
print(f"最新: {chapters[-1].get('title', '?')} ({chapters[-1].get('word_count', 0)}字)")

# 导出 txt
title = "万历新明_穿越篇"
output_path = f"/root/{title}.txt"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(f"《万历新明·穿越篇》\n\n")
    for ch in chapters:
        ch_title = ch.get("title", "")
        ch_content = ch.get("content", "")
        f.write(f"\n{'='*40}\n{ch_title}\n{'='*40}\n\n{ch_content}\n")

import os
size = os.path.getsize(output_path)
print(f"✅ 已导出: {output_path} ({size:,} bytes, {len(chapters)}章)")
