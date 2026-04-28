#!/usr/bin/env python3
"""
AgentSystem 服务启动后自我迭代闭环 E2E
=====================================

目标：
1. 以真实 HTTP 请求验证服务可交互
2. 通过 governance nightly trigger 驱动一次 regression/self-iteration 闭环
3. 验证结果中必须出现 cycle，并允许 rollout 被 apply 或被 preflight 阻断

用法：
  1. 启动服务:
     cd /root/project/AgentSystem && python3 -m uvicorn app.system.http_test_server:app --host 0.0.0.0 --port 8765
  2. 运行脚本:
     python3 tests/scripts/e2e_self_iteration_service_up.py

可选环境变量：
  BASE_URL=http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765").rstrip("/")
USERNAME = "e2e-self-iteration"
PASSWORD = "test123456"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"


class SessionClient:
    def __init__(self) -> None:
        self.s = requests.Session()

    def post(self, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> requests.Response:
        return self.s.post(f"{BASE_URL}{path}", json=json_body, params=params, timeout=120)

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> requests.Response:
        return self.s.get(f"{BASE_URL}{path}", params=params, timeout=120)


def fail(msg: str, payload: Any | None = None) -> None:
    print(f"{RED}FAIL{NC}: {msg}")
    if payload is not None:
        try:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            print(payload)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"{GREEN}OK{NC}: {msg}")


def login(client: SessionClient) -> None:
    resp = client.post("/login", json_body={"username": USERNAME, "password": PASSWORD})
    if resp.status_code != 200:
        fail(f"login status={resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("success"):
        fail("login returned success=false", data)
    ok("login")


def ensure_schedule(client: SessionClient) -> None:
    resp = client.post("/api/governance/regression-cycle/nightly", params={"interval_seconds": 1})
    if resp.status_code != 200:
        fail(f"register nightly schedule status={resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("success"):
        fail("nightly schedule registration failed", data)
    ok("nightly schedule registered")


def chat_probe(client: SessionClient) -> None:
    resp = client.post("/api/chat", json_body={"message": "你好，请简单介绍一下你自己"})
    if resp.status_code != 200:
        fail(f"chat status={resp.status_code}", resp.text)
    data = resp.json()
    text = str(data.get("response") or data.get("content") or "")
    if not text:
        fail("chat returned empty response", data)
    ok("chat interaction works")


def run_self_iteration_cycle(client: SessionClient) -> dict[str, Any]:
    resp = client.post("/api/governance/regression-cycle/nightly/trigger", params={"auto_apply_governance": "true"})
    if resp.status_code != 200:
        fail(f"nightly trigger status={resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("success"):
        fail("nightly trigger returned success=false", data)
    if not data.get("triggered"):
        fail("nightly trigger did not trigger", data)
    cycle = data.get("cycle")
    if not isinstance(cycle, dict) or not cycle.get("run_id"):
        fail("cycle result missing run_id", data)
    return data


def verify_cycle_payload(data: dict[str, Any]) -> None:
    cycle = data["cycle"]
    summary = cycle.get("summary") or {}
    if int(summary.get("topic_count") or 0) <= 0:
        fail("cycle summary missing positive topic_count", data)
    if not cycle.get("trigger_application"):
        fail("cycle missing trigger_application", data)

    governance_rollout = data.get("governance_rollout")
    if governance_rollout is None:
        fail("governance_rollout missing", data)

    if governance_rollout.get("applied") is True:
        ok("governance rollout auto-applied")
        return

    preflight = governance_rollout.get("preflight") or {}
    if preflight.get("can_apply") is not False:
        fail("governance rollout neither applied nor clearly blocked by preflight", data)
    ok(f"governance rollout blocked by preflight: {preflight.get('hold_reason')}")


def fetch_latest_regression(client: SessionClient) -> None:
    resp = client.get("/api/chat-regression/latest")
    if resp.status_code != 200:
        fail(f"latest regression status={resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("success"):
        fail("latest regression returned success=false", data)
    summary = data.get("summary") or {}
    if not summary.get("run_id"):
        fail("latest regression missing run_id", data)
    ok("latest regression retrievable")


def main() -> None:
    print(f"{YELLOW}BASE_URL={BASE_URL}{NC}")
    client = SessionClient()
    login(client)
    ensure_schedule(client)
    chat_probe(client)
    result = run_self_iteration_cycle(client)
    verify_cycle_payload(result)
    fetch_latest_regression(client)
    print(f"{GREEN}SELF-ITERATION SERVICE-UP E2E PASSED{NC}")


if __name__ == "__main__":
    main()
