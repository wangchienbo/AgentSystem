#!/usr/bin/env python3
"""正常用户自然语言请求测试。

模拟真实用户通过 chat 用自然语言驱动系统干活（而非直接调 API 端点），
验证 LLM 意图理解 + 工具/任务触发 + 意图路由正确性。

每个场景用独立 session_id 隔离 continuation 状态，避免互相劫持。
重点检查：请求意图 与 系统响应 是否匹配（意图路由正确性）。

用法：python3 tests/e2e/test_user_natural_language_requests.py [--base URL]
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time

import requests

# (session, user话术, 期望意图类别, 意图匹配关键词)
# 意图类别用于启发式判定响应是否匹配请求
SCENARIOS = [
    ("u1", "你好", "greeting", ["你好", "你好！", "嗨", "在的", "有什么"]),
    ("u2", "你能帮我做什么？", "capability", ["可以", "帮你", "任务", "创建", "写", "查询"]),
    ("u3", "25乘以4等于多少", "math", ["100"]),
    ("u4", "帮我创建一个待办事项App", "create_app", ["app", "创建", "draft", "待办"]),
    ("u5", "帮我写一首关于夏天的短诗", "creative", ["夏", "诗", "首"]),
    ("u6", "系统现在运行健康吗？", "status", ["健康", "正常", "运行", "状态"]),
    ("u7", "我叫小明，请记住我", "memory", ["小明", "记住"]),
    ("u8", "把 hello 翻译成中文", "translate", ["你好"]),
    ("u9", "帮我删除系统里所有App", "boundary", ["删除", "无法", "不能", "安全", "确认", "谨慎"]),
    ("u10", "用一句话解释什么是Agent", "concept", ["Agent", "代理", "智能"]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8765")
    ap.add_argument("--report", default="/tmp/agentsystem_user_requests.json")
    args = ap.parse_args()
    BASE = args.base.rstrip("/")

    sess = requests.Session()
    r = sess.post(BASE + "/login", json={"username": "testuser"}, timeout=15)
    if r.status_code != 200:
        print(f"登录失败 {r.status_code}")
        return 1

    results = []
    print("=" * 70)
    print(f"{'会话':<5}{'用户请求':<22}{'期望意图':<12}{'意图匹配':<8}{'任务/工具触发':<14}")
    print("-" * 70)

    for sid, msg, intent, keywords in SCENARIOS:
        t0 = time.time()
        try:
            rr = sess.post(BASE + "/api/chat",
                           json={"message": msg, "session_id": sid}, timeout=90)
            status = rr.status_code
            lat = (time.time() - t0) * 1000
            try:
                j = rr.json()
            except Exception:
                j = None
        except Exception as e:
            results.append({"session": sid, "msg": msg, "error": str(e)})
            print(f"{sid:<5}{msg:<22}{intent:<12}{'异常':<8}")
            continue

        resp = (j or {}).get("response") or ""
        resp_l = resp.lower()
        # 意图匹配：响应中是否命中期望关键词
        matched = any(k.lower() in resp_l for k in keywords)
        # 任务/工具触发迹象
        data = (j or {}).get("data") or {}
        has_task = bool(data.get("pending_task")) or bool(data.get("continuation_decision"))
        related_app = (j or {}).get("related_app")
        has_action = bool((j or {}).get("actions"))
        triggered = "✓" if (has_task or related_app or has_action) else "—"

        match_mark = "✓" if matched else "✗"
        results.append({
            "session": sid, "msg": msg, "intent": intent,
            "matched": matched, "status": status, "latency_ms": round(lat, 1),
            "has_task": has_task, "related_app": related_app, "has_action": has_action,
            "response": resp,
        })
        print(f"{sid:<5}{msg:<22}{intent:<12}{match_mark:<8}{triggered:<14} [{status} {lat:.0f}ms]")
        print(f"       ↳ 响应: {resp[:120]}")

    # 汇总
    total = len(results)
    matched_n = sum(1 for x in results if x.get("matched"))
    print("=" * 70)
    print(f"总计 {total} 个用户请求 | 意图匹配 {matched_n}/{total} | "
          f"匹配率 {matched_n/total*100:.1f}%")
    print(f"报告: {args.report}")

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.datetime.now().isoformat(),
                   "results": results}, f, ensure_ascii=False, indent=2, default=str)

    # 不因启发式误判直接失败——输出供人工审视；但明确列出未匹配项
    print("\n未匹配意图的请求（需人工审视是否为意图路由问题）:")
    for x in results:
        if not x.get("matched"):
            print(f"  - [{x['session']}] 「{x['msg']}」→ {x.get('response','')[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
