#!/usr/bin/env python3
"""批量续写到 300 章，支持断点续写。"""
import requests, time, json, os, sys, traceback

BASE = "http://localhost:80"
NOVEL_ID = "novel_20260519095419_30f0ac4e"
TARGET_CHAPTERS = 300
TICK_DELAY = 8       # tick 间隔
CHAPTER_DELAY = 8    # 章节间隔
EXPORT_INTERVAL = 10  # 每写 10 章导出一次 txt
LOG_FILE = "/tmp/novel_batch_300.log"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def dispatch(op, params=None, timeout=180):
    try:
        r = requests.post(f"{BASE}/api/task/dispatch",
            json={"app":"novel_studio","operation":op,"params":params or {}},
            timeout=30)
        data = r.json()
        if not data.get("success"):
            log(f"  dispatch failed: {data}")
            return None
        tid = data["task"]["task_id"]
        for _ in range(timeout // 2):
            time.sleep(2)
            t = requests.get(f"{BASE}/api/task/{tid}", timeout=30).json().get("task", {})
            if t.get("status") == "done":
                return t.get("result") or {}
            if t.get("status") == "failed":
                log(f"  task failed: {t.get('error')}")
                return None
        log(f"  task timeout after {timeout}s")
        return None
    except Exception as e:
        log(f"  dispatch error: {e}")
        return None

def get_chapters():
    r = requests.post(f"{BASE}/api/novel/get", json={"novel_id": NOVEL_ID}, timeout=30)
    return r.json().get("novel", {}).get("chapters", [])

def export_txt(chapters):
    output_path = "/root/万历新明_穿越篇.txt"
    static_path = "/root/projects/AgentSystem/static/万历新明_穿越篇.txt"
    content = f"《万历新明·穿越篇》\n\n"
    for ch in chapters:
        t = ch.get("title", "")
        c = ch.get("content", "")
        content += f"\n{'='*40}\n{t}\n{'='*40}\n\n{c}\n"
    for p in [output_path, static_path]:
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    size = os.path.getsize(output_path)
    return size

# --- Main ---
log("=" * 50)
log(f"批量续写启动，目标: {TARGET_CHAPTERS} 章")

chapters = get_chapters()
current = len(chapters)
log(f"当前已有 {current} 章")

if current >= TARGET_CHAPTERS:
    log("已达目标，退出")
    sys.exit(0)

written_since_export = 0
errors_in_a_row = 0

for i in range(current, TARGET_CHAPTERS):
    ch_num = i + 1
    try:
        # tick x2
        for t in range(2):
            dispatch("tick")
            time.sleep(TICK_DELAY)

        # 写章节
        result = dispatch("write_narrative_chapter")
        new_chapters = get_chapters()
        new_count = len(new_chapters)

        if new_count > i:
            ch = new_chapters[-1]
            title = ch.get("title", "?")
            wc = ch.get("word_count", 0)
            log(f"[{ch_num}/{TARGET_CHAPTERS}] ✅ {title} ({wc}字)")
            errors_in_a_row = 0
            written_since_export += 1
        else:
            log(f"[{ch_num}/{TARGET_CHAPTERS}] ⚠️ 章节数未变 ({i}→{new_count})")
            errors_in_a_row += 1
            if errors_in_a_row >= 5:
                log("连续 5 次失败，暂停 60 秒")
                time.sleep(60)
                errors_in_a_row = 0
                continue

        # 定期导出
        if written_since_export >= EXPORT_INTERVAL:
            size = export_txt(new_chapters)
            log(f"📦 导出 txt ({new_count}章, {size:,} bytes)")
            written_since_export = 0

        time.sleep(CHAPTER_DELAY)

    except KeyboardInterrupt:
        log("手动中断，导出当前进度...")
        chapters = get_chapters()
        size = export_txt(chapters)
        log(f"📦 导出 txt ({len(chapters)}章, {size:,} bytes)")
        sys.exit(0)
    except Exception as e:
        log(f"❌ 异常: {e}")
        traceback.print_exc()
        errors_in_a_row += 1
        time.sleep(30)

# 最终导出
chapters = get_chapters()
size = export_txt(chapters)
total_words = sum(c.get("word_count", 0) for c in chapters)
log(f"🎉 完成！共 {len(chapters)} 章, {total_words:,} 字, 文件 {size:,} bytes")
