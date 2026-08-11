#!/usr/bin/env python3
"""50 轮真实服务端到端冒烟测试（HTTP API + 真实 LLM）。

与 tests/e2e/test_50_scenarios_20_turns.py（架构层、不依赖外部 LLM）互补：
本脚本针对**真实运行的 uvicorn 服务**做 50 轮 HTTP 往返，覆盖
  A. 真实 LLM 对话（gateway /api/chat + novel chat）
  B. novel_studio 数据层 CRUD（create/list/get/outline/character/world/scene）
  C. 会话/状态端点（history/tasks）
  D. 错误处理鲁棒性（非法输入/不存在资源/错误 method —— 断言零 5xx）
  E. 稳定性压力（重复 list/chat/health 无劣化）

用法（先启动服务: agentsystem serve --port 8765）：
  python3 tests/e2e/test_50_rounds_api_smoke.py                 # 完整 50 轮(含真实 LLM)
  python3 tests/e2e/test_50_rounds_api_smoke.py --skip-llm      # 快速巡检,不调 LLM(省成本)
  python3 tests/e2e/test_50_rounds_api_smoke.py --rounds 20 --base http://localhost:8765

退出码: 0=全部通过, 1=有失败。报告 JSON 落在 --report 指定路径。
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time

import requests

# 默认 50 轮矩阵中真实 LLM 轮次（chat）
CHAT_MESSAGES = [
    "你好，请用一句话自我介绍",
    "请复述这句话：系统端到端测试第2轮",
    "请计算 17*23 等于多少，只给数字",
    "把这句话翻译成英文：你好，世界",
    "请用三个词描述你自己",
    "1+1等于几？",
    "请介绍你能帮我做哪三类事",
    "请列出三种编程语言",
    "用一句话解释什么是面向对象编程",
    "请把 abcdef 倒序输出",
    "如果昨天是星期天，那么今天是星期几",
    "请原样重复我这句话：稳定性验证OK",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="AgentSystem 50 轮真实服务端到端冒烟测试")
    ap.add_argument("--base", default="http://localhost:8765")
    ap.add_argument("--rounds", type=int, default=50)
    ap.add_argument("--skip-llm", action="store_true", help="跳过真实 LLM 轮次(省成本,用于快速巡检)")
    ap.add_argument("--report", default="/tmp/agentsystem_50rounds_report.json")
    args = ap.parse_args()

    BASE = args.base.rstrip("/")
    results: list[dict] = []

    def log(msg: str) -> None:
        print(msg, flush=True)

    def call(sess, method, path, body=None, raw_body=None, timeout=90):
        url = BASE + path
        headers = {"Content-Type": "application/json"}
        t0 = time.time()
        try:
            if raw_body is not None:
                r = sess.request(method, url, data=raw_body, headers=headers, timeout=timeout)
            else:
                r = sess.request(method, url, json=body, headers=headers, timeout=timeout)
            lat = (time.time() - t0) * 1000
            try:
                j = r.json()
            except Exception:
                j = None
            return r.status_code, j, lat
        except Exception as e:  # noqa: BLE001
            return -1, {"_exc": str(e)}, (time.time() - t0) * 1000

    def record(i, name, status, j, latency, passed, detail=""):
        results.append({
            "round": i, "name": name, "status": status, "passed": passed,
            "latency_ms": round(latency, 1), "detail": detail[:200],
        })
        mark = "PASS" if passed else "FAIL"
        log(f"[{i:>2}/{args.rounds}] {mark} {name} -> HTTP {status} ({latency:.0f}ms)"
            + (f" | {detail}" if detail else ""))

    sess = requests.Session()
    r = sess.post(BASE + "/login", json={"username": "testuser"}, timeout=15)
    if r.status_code != 200:
        log(f"❌ 登录失败: HTTP {r.status_code}（确认服务已启动: {BASE}）")
        return 1
    log(f"登录成功, session cookie: {list(sess.cookies.get_dict().keys())}")

    stamp = datetime.datetime.now().strftime("%H%M%S")
    n1 = f"E2E小说A-{stamp}"
    n2 = f"E2E小说B-{stamp}"
    n1_id = n2_id = None
    created_ids: list[str] = []
    rnd = [0]  # 当前轮次计数器（闭包共享）

    def run(name, method, path, body=None, raw_body=None,
            expect="success", verify=None, timeout=90):
        rnd[0] += 1
        i = rnd[0]
        status, j, lat = call(sess, method, path, body, raw_body, timeout)
        passed = False
        detail = ""
        if status == -1:
            detail = f"异常:{j.get('_exc', '')}"
        elif expect == "success":
            passed = (status == 200 and isinstance(j, dict) and j.get("success") is True)
            if not passed:
                detail = f"resp={json.dumps(j, ensure_ascii=False)[:120]}"
        elif expect == "ok":
            passed = (200 <= status < 300)
            if not passed:
                detail = f"status={status}"
        elif expect == "error":
            passed = (400 <= status < 500) or (isinstance(j, dict)
                                               and (j.get("success") is False or "error" in j))
            if 500 <= status < 600:
                passed = False
            if not passed:
                detail = f"status={status} resp={json.dumps(j, ensure_ascii=False)[:120]}"
        elif expect == "no5xx":
            passed = not (500 <= status < 600)
            if not passed:
                detail = f"status={status} resp={json.dumps(j, ensure_ascii=False)[:120]}"
        if verify and passed:
            try:
                ok, vd = verify(j)  # verify 必须返回 (ok: bool, detail: str)
                if not ok:
                    passed = False
                    detail = vd
            except Exception as e:  # noqa: BLE001
                passed = False
                detail = f"verify exc:{e}"
        record(i, name, status, j, lat, passed, detail)
        return j

    # ============ A. 真实 LLM chat ============
    chats = CHAT_MESSAGES if not args.skip_llm else []
    for msg in chats:
        run(f"chat", "POST", "/api/chat", {"message": msg}, expect="success",
            verify=lambda j: ((j.get("response") or "").strip() != "", "response 为空"), timeout=90)

    # ============ B. novel_studio 数据层 CRUD ============
    rj = run("novel/create-A", "POST", "/api/novel/create",
             {"title": n1, "genre": "玄幻", "author": "e2e", "logline": "测试梗概"})
    if isinstance(rj, dict) and rj.get("novel_id"):
        n1_id = rj["novel_id"]; created_ids.append(n1_id)
    rj = run("novel/create-B", "POST", "/api/novel/create", {"title": n2, "genre": "都市"})
    if isinstance(rj, dict) and rj.get("novel_id"):
        n2_id = rj["novel_id"]; created_ids.append(n2_id)

    def v_list(j):
        titles = [n.get("title") for n in (j.get("novels") or [])]
        return (n1 in titles and n2 in titles), f"缺:{n1}/{n2}"
    run("novel/list", "POST", "/api/novel/list", {}, expect="success", verify=v_list)

    if n1_id:
        run("novel/get-A", "POST", "/api/novel/get", {"novel_id": n1_id},
            verify=lambda j: (j.get("novel", {}).get("title") == n1, "title"))
        run("novel/outline-A", "POST", "/api/novel/outline", {"novel_id": n1_id},
            verify=lambda j: (j.get("has_outline") is True, "has_outline"))
        run("novel/outline-save", "POST", "/api/novel/outline/save",
            {"novel_id": n1_id, "summary": "三段式",
             "three_act": {"act1": "起", "act2": "承", "act3": "合"}})
        run("novel/outline-chapter", "POST", "/api/novel/outline/chapter",
            {"novel_id": n1_id, "number": 1, "title": "第一章", "summary": "开场"})
        run("novel/characters-empty", "POST", "/api/novel/characters", {"novel_id": n1_id})
        run("novel/character-add", "POST", "/api/novel/character/add",
            {"novel_id": n1_id, "name": "主角", "archetype": "主角", "personality": ["坚毅"]})
        run("novel/characters-has", "POST", "/api/novel/characters", {"novel_id": n1_id},
            verify=lambda j: ("主角" in [c.get("name") for c in (j.get("characters") or [])], "chars"))
        run("novel/world-get", "POST", "/api/novel/world", {"novel_id": n1_id})
        run("novel/world-save", "POST", "/api/novel/world/save",
            {"novel_id": n1_id, "name": "测试世界", "overview": "概述", "rules": ["规则1"]})
        run("novel/scene-add", "POST", "/api/novel/scene/add",
            {"novel_id": n1_id, "name": "开场场景", "location": "城", "description": "描述"})
        run("novel/report", "POST", "/api/novel/report", {"novel_id": n1_id})

    # ============ C. 会话/状态 ============
    run("sys/chat-history", "GET", "/api/history/session_testuser", expect="ok")
    run("novel/tasks-latest", "GET", "/api/novel/tasks/latest", expect="ok")
    if n2_id:
        run("novel/get-B", "POST", "/api/novel/get", {"novel_id": n2_id},
            verify=lambda j: (j.get("novel", {}).get("title") == n2, "title"))
    run("novel/chat-history", "POST", "/api/novel/chat/history", {"novel_id": n1_id or "x"}, expect="ok")

    # ============ D. 错误处理鲁棒性 ============
    run("err/chat-empty-message", "POST", "/api/chat", {"message": ""}, expect="no5xx")
    run("err/chat-missing-field", "POST", "/api/chat", {}, expect="no5xx")
    run("err/get-nonexistent", "POST", "/api/novel/get", {"novel_id": "nope_12345"}, expect="error")
    run("err/outline-save-nonexistent", "POST", "/api/novel/outline/save", {"novel_id": "nope_12345"}, expect="error")
    run("err/create-empty-title", "POST", "/api/novel/create", {"title": ""}, expect="no5xx")
    run("err/delete-nonexistent", "POST", "/api/novel/delete", {"novel_id": "nope_12345"}, expect="no5xx")
    run("err/invalid-json", "POST", "/api/novel/list", raw_body="{not valid json", expect="no5xx")
    run("err/wrong-method", "GET", "/api/novel/create", expect="no5xx")
    run("err/char-update-nonexistent", "POST", "/api/novel/character/update",
        {"novel_id": "nope_12345", "char_id": "x"}, expect="error")
    run("err/chapter-add-nonexistent", "POST", "/api/novel/chapter/add",
        {"novel_id": "nope_12345", "title": "x"}, expect="error")
    run("err/task-nonexistent", "GET", "/api/novel/task/no_such_task", expect="no5xx")
    run("err/chat-huge", "POST", "/api/chat", {"message": "长" * 2000}, expect="no5xx", timeout=120)

    # ============ E. 稳定性压力 ============
    while rnd[0] < args.rounds:
        k = rnd[0]
        if k % 3 == 0:
            run(f"stress/list[{k}]", "POST", "/api/novel/list", {}, expect="success")
        elif k % 3 == 1:
            if args.skip_llm:
                run(f"stress/health[{k}]", "GET", "/", expect="ok")
            else:
                run(f"stress/chat[{k}]", "POST", "/api/chat", {"message": "回复OK两个字"},
                    expect="success",
                    verify=lambda j: ((j.get("response") or "").strip() != "", "response 为空"), timeout=90)
        else:
            run(f"stress/health[{k}]", "GET", "/", expect="ok")

    # ============ 清理 ============
    for nid in created_ids:
        try:
            sess.post(BASE + "/api/novel/delete", json={"novel_id": nid}, timeout=15)
        except Exception:  # noqa: BLE001
            log(f"⚠️ 清理失败 {nid}")

    # ============ 汇总 ============
    passed = sum(1 for r_ in results if r_["passed"])
    total = len(results)
    fails = [r_ for r_ in results if not r_["passed"]]
    avg_lat = sum(r_["latency_ms"] for r_ in results) / max(total, 1)
    report = {
        "generated_at": datetime.datetime.now().isoformat(),
        "base": BASE, "skip_llm": args.skip_llm,
        "total": total, "passed": passed, "failed": total - passed,
        "pass_rate": f"{passed / total * 100:.1f}%" if total else "0%",
        "avg_latency_ms": round(avg_lat, 1),
        "failures": fails, "results": results,
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    log("\n" + "=" * 60)
    log(f"总计 {total} 轮 | 通过 {passed} | 失败 {total - passed} | 通过率 {passed / total * 100:.1f}%")
    log(f"平均延迟 {avg_lat:.0f}ms | 报告: {args.report}")
    if fails:
        log("失败明细:")
        for fr in fails:
            log(f"  - R{fr['round']} {fr['name']} HTTP {fr['status']} | {fr['detail']}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
