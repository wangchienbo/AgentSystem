import requests, time, json, os

BASE = "http://localhost:80"
NOVEL_ID = "novel_20260519095419_30f0ac4e"
COUNT = 5

def dispatch(op, params=None, timeout=180):
    r = requests.post(f"{BASE}/api/task/dispatch", json={"app":"novel_studio","operation":op,"params":params or {}}, timeout=30)
    tid = r.json()["task"]["task_id"]
    for _ in range(timeout // 2):
        time.sleep(2)
        t = requests.get(f"{BASE}/api/task/{tid}", timeout=30).json().get("task", {})
        if t["status"] == "done": return t.get("result")
        if t["status"] == "failed": print(f"  FAIL: {t.get('error')}"); return None
    return None

def get_chs():
    return requests.post(f"{BASE}/api/novel/get", json={"novel_id":NOVEL_ID}, timeout=30).json().get("novel",{}).get("chapters",[])

# 加载小说
print("load_novel...", flush=True)
dispatch("load_novel", {"novel_id": NOVEL_ID})
time.sleep(2)

# 初始化演化
print("init_evolution...", flush=True)
dispatch("init_evolution", {"novel_id": NOVEL_ID})
time.sleep(5)

start = len(get_chs())
print(f"起始: {start}章, 写{COUNT}章", flush=True)

for i in range(COUNT):
    ch = start + i + 1
    dispatch("tick"); time.sleep(5)
    dispatch("tick"); time.sleep(5)
    print(f"写第{ch}章...", end="", flush=True)
    r = dispatch("write_narrative_chapter", timeout=300)
    ch_data = (r or {}).get("chapter", r or {})
    title = ch_data.get("title", "?")
    wc = ch_data.get("word_count", 0)
    print(f" {title} ({wc}字)", flush=True)
    time.sleep(3)

chs = get_chs()
total = sum(c.get("word_count", 0) for c in chs)
print(f"\n完成: {len(chs)}章, {total}字", flush=True)

# 导出
with open("/root/万历新明_穿越篇.txt", "w", encoding="utf-8") as f:
    f.write("《万历新明·穿越篇》\n\n")
    for c in chs:
        f.write(f"\n{'='*40}\n{c.get('title','')}\n{'='*40}\n\n{c.get('content','')}\n")
print(f"导出: {os.path.getsize('/root/万历新明_穿越篇.txt'):,} bytes", flush=True)
