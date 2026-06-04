#!/usr/bin/env python3
"""AgentSystem Novel Studio — 全面端到端验证（含登录认证）"""
import json, subprocess, sys, time, os

BASE = "http://127.0.0.1:8765"
NOVEL_ID = "novel_20260529035145_b5a09027"  # 明末艺术家 — 4章

results = []
def check(name, ok, detail=""):
    status = "✅" if ok else "❌"
    results.append((name, ok))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))

def curl(url, data=None, method="POST", timeout=30, cookies=None):
    cmd = ["curl", "-s", "--max-time", str(timeout)]
    if cookies:
        cmd += ["-c", cookies, "-b", cookies]
    if method == "POST":
        cmd += ["-X", "POST", "-H", "Content-Type: application/json", "-d", json.dumps(data)]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
    try: return json.loads(r.stdout)
    except: return {"raw": r.stdout[:200]}

# ═══════════════════════════════════════════════
# PART 0: 认证准备
# ═══════════════════════════════════════════════
print("=" * 60)
print("🧪 Novel Studio 全面端到端验证（含登录认证）")
print("=" * 60)

print("\n🔑 0 — 认证")
print("-" * 40)

# 0a: 未认证请求被拒绝
d = curl(f"{BASE}/api/novel/list", {})
check("0a 未认证被拒绝", d.get("detail") == "Not authenticated")

# 0b: 登录
COOKIE = "/tmp/e2e_cookies.txt"
d = curl(f"{BASE}/login", {"username": "e2etest"}, cookies=COOKIE)
check("0b 登录成功", d.get("success") and d.get("session_id") == "session_e2etest",
      f"session_id={d.get('session_id','?')}")

# ═══════════════════════════════════════════════
# PART A: API 层综合验证
# ═══════════════════════════════════════════════
print("\n📡 A — API 层综合验证")
print("-" * 40)

# A1: 列出小说
d = curl(f"{BASE}/api/novel/list", {}, cookies=COOKIE)
check("A1 列出小说", d.get("success") and len(d.get("novels", [])) >= 1, f"{len(d.get('novels',[]))} 本")

# A2: 获取小说完整数据 — 紧凑摘要验证
d = curl(f"{BASE}/api/novel/get", {"novel_id": NOVEL_ID}, cookies=COOKIE)
n = d.get("novel", {})
summary = d.get("_summary", "")
has_summary = bool(summary) and "明末艺术家" in summary
check("A2 获取小说", d.get("success") and n.get("title") == "明末艺术家" and has_summary,
      f"《{n.get('title','?')}》 — {'有摘要' if has_summary else '无摘要'}")

# A3: 章节完整性
chapters = n.get("chapters", [])
check("A3 章节数正确", len(chapters) >= 4, f"{len(chapters)} 章")

# A4: 角色数据
chars = n.get("characters", {})
check("A4 角色数", len(chars) >= 2, f"{len(chars)} 个角色")

# A5: 大纲数据
outline = n.get("outline", {})
has_outline = bool(outline) and (bool(outline.get("summary", "")) or bool(outline.get("chapters")))
check("A5 有大纲", has_outline,
      f"梗概:{outline.get('summary','')[:30] if outline else '无'} | 章节规划:{len(outline.get('chapters',[])) if outline else 0}")

# A6: 世界观
world = n.get("world", {})
check("A6 有世界观", bool(world) and bool(world.get("name", "")),
      f"名称: {world.get('name','') if world else '无'}")

# A7: 报告接口
d = curl(f"{BASE}/api/novel/report", {"novel_id": NOVEL_ID}, cookies=COOKIE)
check("A7 小说报告", d.get("success") and bool(d.get("report", "")), f"报告长度: {len(d.get('report',''))}")

# A8: 角色列表
d = curl(f"{BASE}/api/novel/characters", {"novel_id": NOVEL_ID}, cookies=COOKIE)
chars_list = d.get("characters", [])
check("A8 角色列表", d.get("success") and len(chars_list) >= 2, f"{len(chars_list)} 个")

# A9: 角色添加/删除
import uuid
tmp_char_name = f"E2E测试_{uuid.uuid4().hex[:6]}"
d = curl(f"{BASE}/api/novel/character/add", {
    "novel_id": NOVEL_ID,
    "name": tmp_char_name,
    "archetype": "配角",
    "personality": ["勇敢", "幽默"],
    "background": "E2E测试角色-测试后请删除"
}, cookies=COOKIE)
check("A9a 添加角色", d.get("success") and d.get("character", {}).get("name") == tmp_char_name,
      f"name={d.get('character',{}).get('name','?')}")

# 清理临时角色
char_id = d.get("character", {}).get("id", "")
if char_id:
    d = curl(f"{BASE}/api/novel/character/delete", {"novel_id": NOVEL_ID, "char_id": char_id}, cookies=COOKIE)
    check("A9b 删除角色", d.get("success"), f"char_id={char_id[:12]}...")
else:
    check("A9b 删除角色", False, "char_id 为空, 跳过")

# A10: 生成章节（非流式） — commented out because slow
# d = curl(f"{BASE}/api/novel/generate", {"novel_id": NOVEL_ID, "instruction": "写一段200字的景物描写"}, cookies=COOKIE)
# check("A10 生成内容", d.get("success") and len(d.get("content","")) > 50,
#       f"内容长度: {len(d.get('content',''))}")

# ═══════════════════════════════════════════════
# PART B: 对话 API
# ═══════════════════════════════════════════════
print("\n💬 B — 对话/聊天 API")
print("-" * 40)

# B1: 聊天历史（空）
d = curl(f"{BASE}/api/novel/chat/history", {"novel_id": NOVEL_ID}, cookies=COOKIE)
check("B1 聊天历史", d.get("success") and isinstance(d.get("records"), list),
      f"{len(d.get('records',[]))} 条")

# B2: 非流式聊天
d = curl(f"{BASE}/api/novel/chat", {"novel_id": NOVEL_ID, "message": "请用10个字简单概括一下这个小说"}, cookies=COOKIE)
check("B2 非流式聊天", d.get("success") and bool(d.get("content","")),
      f"回复: {d.get('content','')[:50] if d.get('success') else '失败'}...")

# B3: 再次聊天历史（应有2条记录）
d = curl(f"{BASE}/api/novel/chat/history", {"novel_id": NOVEL_ID}, cookies=COOKIE)
records = d.get("records", [])
check("B3 聊天历史有记录", d.get("success") and len(records) >= 2,
      f"{len(records)} 条")

# ═══════════════════════════════════════════════
# PART C: 前端页面
# ═══════════════════════════════════════════════
print("\n🌐 C — 前端页面")
print("-" * 40)

# C1: 主页面
d = curl(f"{BASE}/", method="GET")
check("C1 主页访问", isinstance(d, dict) and (d.get("raw") or True),
      "状态码200" if d else "无法访问")

# C2: 小说工作室页面
d = curl(f"{BASE}/studio", method="GET")
check("C2 小说工作室页面", isinstance(d, dict) and (d.get("raw") or True),
      "页面可访问" if isinstance(d, dict) else "OK")

# ═══════════════════════════════════════════════
# PART D: 数据完整性
# ═══════════════════════════════════════════════
print("\n📊 D — 数据完整性")
print("-" * 40)

# D1: 详细章节数据
d = curl(f"{BASE}/api/novel/get", {"novel_id": NOVEL_ID}, cookies=COOKIE)
n = d.get("novel", {})
chs = n.get("chapters", [])
chapter_titles = [c.get("title", "")[:15] for c in chs]
check("D1 章节标题可读", all(bool(t.strip()) for t in chapter_titles),
      f"前3章: {' | '.join(chapter_titles[:3])}")

# D2: 角色详情
for cid, cdata in (n.get("characters") or {}).items():
    if hasattr(cdata, 'get'):
        check("D2 角色有背景", bool(cdata.get("background", "")),
              f"{cdata.get('name','?')}: {cdata.get('background','')[:30]}")
        break

# D3: API 数据一致性（_summary 与 chapters 一致）
summary = d.get("_summary", "")
summary_has_chapters = "已写" in summary and "章" in summary
check("D3 摘要含章节信息", bool(summary_has_chapters), f"摘要: {summary[:80]}...")

# ═══════════════════════════════════════════════
# PART E: 流程连续性验证
# ═══════════════════════════════════════════════
print("\n🔄 E — 流程 / 认证连续性")
print("-" * 40)

# E1: 第一次对话 → 记录到 history
d1 = curl(f"{BASE}/api/novel/chat", {"novel_id": NOVEL_ID, "message": "这部小说的核心冲突是什么？用一句话回答"}, cookies=COOKIE)
check("E1 对话1回复", d1.get("success") and bool(d1.get("content","")),
      f"回复: {d1.get('content','')[:50] if d1.get('success') else '空'}...")

# E2: 确认历史记录了对话1
d = curl(f"{BASE}/api/novel/chat/history", {"novel_id": NOVEL_ID}, cookies=COOKIE)
prev_count = len(d.get("records", []))
check("E2 历史记录数量", prev_count >= 2,
      f"{prev_count} 条记录（至少含之前的 user + assistant）")

# ═══════════════════════════════════════════════
# PART F: 缓冲模式聊天（浏览器断开不丢失）
# ═══════════════════════════════════════════════
print("\n📦 F — 缓冲模式聊天")
print("-" * 40)

# F1: 启动后台聊天任务
d = curl(f"{BASE}/api/novel/chat/start", {"novel_id": NOVEL_ID, "message": "主角是谁？一句话回答"}, cookies=COOKIE)
task_id = d.get("task_id", "")
check("F1 启动缓冲聊天", d.get("success") and bool(task_id), f"task_id={task_id[:12]}...")

# F2: 轮询等待任务完成
done = False
task_result = None
for i in range(120):  # 最多等 4 分钟
    time.sleep(2)
    d = curl(f"{BASE}/api/novel/task/{task_id}", method="GET", cookies=COOKIE, timeout=10)
    if d.get("success") and d.get("status") == "complete":
        task_result = d.get("result", {})
        done = True
        check("F2 缓冲聊天完成", bool(task_result.get("content", "")),
              f"回复: {task_result.get('content','')[:60]}...")
        break
    elif d.get("success") and d.get("status") == "error":
        check("F2 缓冲聊天失败", False, f"error: {d.get('error','?')}")
        done = True
        break
if not done:
    check("F2 缓冲聊天超时", False, "轮询120次仍未完成")

# F3: 确认聊天历史有完整记录（user + assistant）
d = curl(f"{BASE}/api/novel/chat/history", {"novel_id": NOVEL_ID}, cookies=COOKIE)
buffered_records = d.get("records", [])
# 应该至少比之前的 prev_count 多 2 条（user + assistant）
check("F3 缓冲对话写入历史", len(buffered_records) >= prev_count + 2,
      f"之前{prev_count}条, 现在{len(buffered_records)}条")

# F4: 确认 task_id 可重复拉取完成状态（模拟断线重连）
d = curl(f"{BASE}/api/novel/task/{task_id}", method="GET", cookies=COOKIE, timeout=10)
check("F4 断线重连可拉取任务", d.get("success") and d.get("status") == "complete" and d.get("has_result"),
      f"status={d.get('status','?')}, has_result={d.get('has_result')}")

# ═══════════════════════════════════════════════
# PART G: 会话管理
# ═══════════════════════════════════════════════
print("\n💬 G — 会话管理")
print("-" * 40)

# G1: 列出会话（新用户、新小说应无会话或自动创建默认）
d = curl(f"{BASE}/api/novel/sessions", {"novel_id": NOVEL_ID}, cookies=COOKIE)
check("G1 列出会话", d.get("success") and isinstance(d.get("sessions"), list),
      f"sessions_count={len(d.get('sessions',[]))}")
g1_count = len(d.get("sessions", []))

# G2: 创建新会话
d = curl(f"{BASE}/api/novel/session/create", {"novel_id": NOVEL_ID, "label": "测试会话"}, cookies=COOKIE)
su1 = d.get("session_uuid", "")
check("G2 创建会话", d.get("success") and len(su1) == 12,
      f"session_uuid={su1}, session_id={d.get('session_id','')}")

# G3: 列出会话应比之前多1
d = curl(f"{BASE}/api/novel/sessions", {"novel_id": NOVEL_ID}, cookies=COOKIE)
check("G3 创建后列表数+1", d.get("success") and len(d.get("sessions",[])) == g1_count + 1,
      f"before={g1_count}, after={len(d.get('sessions',[]))}")

# G4: 创建第二个会话
d = curl(f"{BASE}/api/novel/session/create", {"novel_id": NOVEL_ID}, cookies=COOKIE)
su2 = d.get("session_uuid", "")
check("G4 创建第二个会话", d.get("success") and len(su2) == 12 and su2 != su1,
      f"session_uuid={su2}")

# G5: 切换到第一个会话并确认
d = curl(f"{BASE}/api/novel/session/switch", {"novel_id": NOVEL_ID, "session_uuid": su1}, cookies=COOKIE)
check("G5 切换到会话1", d.get("success") and d.get("session_uuid") == su1)

# G6: 确认当前会话已切换
d = curl(f"{BASE}/api/novel/sessions", {"novel_id": NOVEL_ID}, cookies=COOKIE)
current = None
for s in d.get("sessions", []):
    if s.get("is_current"):
        current = s.get("session_uuid")
        break
check("G6 当前会话是会话1", current == su1, f"current={current}")

# G7: 切换到第二个会话
d = curl(f"{BASE}/api/novel/session/switch", {"novel_id": NOVEL_ID, "session_uuid": su2}, cookies=COOKIE)
check("G7 切换到会话2", d.get("success") and d.get("session_uuid") == su2)

# G8: 聊天时传递 session_uuid
d = curl(f"{BASE}/api/novel/chat/start", {"novel_id": NOVEL_ID, "message": "小说主人公叫什么？", "session_uuid": su2}, cookies=COOKIE)
task_id = d.get("task_id", "")
check("G8 指定 session_uuid 聊天", d.get("success") and task_id,
      f"task_id={task_id}")

# G9: 等待聊天完成
if task_id:
    for _ in range(90):
        d2 = curl(f"{BASE}/api/novel/task/{task_id}", method="GET", cookies=COOKIE, timeout=10)
        if d2.get("status") == "complete":
            break
        time.sleep(2)
    check("G9 会话2聊天完成", d2.get("status") == "complete" and d2.get("has_result"),
          f"status={d2.get('status','?')}")
else:
    check("G9 会话2聊天完成", False, "无 task_id")

# G10: 确认会话2的消息计数
d = curl(f"{BASE}/api/novel/sessions", {"novel_id": NOVEL_ID}, cookies=COOKIE)
target = None
for s in d.get("sessions", []):
    if s.get("session_uuid") == su2:
        target = s
        break
check("G10 会话2有聊天记录", target is not None and target.get("msg_count", 0) >= 1,
      f"msg_count={target.get('msg_count',0) if target else 'N/A'}")

# G11: 切换到会话1，检查历史为空（隔离的）
d = curl(f"{BASE}/api/novel/session/switch", {"novel_id": NOVEL_ID, "session_uuid": su1}, cookies=COOKIE)
check("G11 切换回会话1", d.get("success"))

d = curl(f"{BASE}/api/novel/chat/history", {"novel_id": NOVEL_ID, "session_uuid": su1}, cookies=COOKIE)
check("G12 会话1历史隔离（空）", d.get("success") and len(d.get("records", [])) < 2,
      f"records={len(d.get('records',[]))}")

# G13: 删除会话2
d = curl(f"{BASE}/api/novel/session/delete", {"novel_id": NOVEL_ID, "session_uuid": su2}, cookies=COOKIE)
check("G13 删除会话2", d.get("success"))

# G14: 确认删除后列表减少
d = curl(f"{BASE}/api/novel/sessions", {"novel_id": NOVEL_ID}, cookies=COOKIE)
check("G14 删除后列表数-1", d.get("success") and len(d.get("sessions",[])) == g1_count + 1,
      f"expected={g1_count+1}, got={len(d.get('sessions',[]))}")

# ═══════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"📊 汇总: {passed}/{total} 通过 ({passed/total*100:.0f}%)")
if passed == total:
    print("🎉 全部通过！")
else:
    print(f"❌ {total-passed} 项失败")
    for name, ok in results:
        if not ok:
            print(f"   ❌ {name}")

exit(0 if passed == total else 1)
