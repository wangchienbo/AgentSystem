#!/usr/bin/env python3
"""
AgentSystem 服务启动后自我迭代闭环 E2E
=====================================

目标：
1. 以真实 HTTP 请求验证服务可交互
2. 验证 draft continuation -> `/api/action` -> running activation 的 HTTP 闭环
3. 通过 governance nightly trigger 驱动一次 regression/self-iteration 闭环
4. 验证结果中必须出现 cycle，并允许 rollout 被 apply 或被 preflight 阻断

用法：
  1. 直接运行（脚本会自启动临时服务）:
     python3 tests/scripts/e2e_self_iteration_service_up.py

可选环境变量：
  BASE_URL=http://127.0.0.1:8765
  START_SERVER=0   # 复用外部已启动服务时可关闭内置启动
"""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765").rstrip("/")
START_SERVER = os.environ.get("START_SERVER", "1") != "0"
USERNAME = "e2e-self-iteration"
PASSWORD = "test123456"
ROOT_DIR = Path(__file__).resolve().parents[2]
SERVER_LOG = ROOT_DIR / "data" / "e2e_self_iteration_service_up.log"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"


class SessionClient:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.session_id: str | None = None

    def post(self, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> requests.Response:
        return self.s.post(f"{BASE_URL}{path}", json=json_body, params=params, timeout=120)

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> requests.Response:
        return self.s.get(f"{BASE_URL}{path}", params=params, timeout=120)


_SERVER_PROCESS: subprocess.Popen[str] | None = None
_SERVER_LOG_HANDLE = None


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
    sys.stdout.flush()


def stage(msg: str) -> None:
    print(f"{YELLOW}STAGE{NC}: {msg}")
    sys.stdout.flush()


def ensure_server_ready(timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/api/status", timeout=3)
            if response.status_code == 200:
                ok("server is ready")
                return
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    fail("server did not become ready in time", str(last_error) if last_error else None)


def _cleanup_server() -> None:
    global _SERVER_PROCESS, _SERVER_LOG_HANDLE
    if _SERVER_PROCESS is not None and _SERVER_PROCESS.poll() is None:
        _SERVER_PROCESS.terminate()
        try:
            _SERVER_PROCESS.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _SERVER_PROCESS.kill()
    if _SERVER_LOG_HANDLE is not None:
        _SERVER_LOG_HANDLE.close()
    _SERVER_PROCESS = None
    _SERVER_LOG_HANDLE = None


def start_server_if_needed() -> None:
    global _SERVER_PROCESS, _SERVER_LOG_HANDLE
    if not START_SERVER:
        ensure_server_ready()
        return
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    _SERVER_LOG_HANDLE = SERVER_LOG.open("w", encoding="utf-8")
    _SERVER_PROCESS = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.system.http_test_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        cwd=str(ROOT_DIR),
        stdout=_SERVER_LOG_HANDLE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    atexit.register(_cleanup_server)
    ensure_server_ready()


def login(client: SessionClient) -> None:
    stage("login")
    resp = client.post("/login", json_body={"username": USERNAME, "password": PASSWORD})
    if resp.status_code != 200:
        fail(f"login status={resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("success"):
        fail("login returned success=false", data)
    client.session_id = data.get("session_id")
    ok("login")


def ensure_schedule(client: SessionClient) -> None:
    stage("register nightly schedule")
    resp = client.post("/api/governance/regression-cycle/nightly", params={"interval_seconds": 1})
    if resp.status_code != 200:
        fail(f"register nightly schedule status={resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("success"):
        fail("nightly schedule registration failed", data)
    ok("nightly schedule registered")


def chat_probe(client: SessionClient) -> None:
    stage("chat probe")
    resp = client.post("/api/chat", json_body={"message": "创建一个笔记 app"})
    if resp.status_code != 200:
        fail(f"chat status={resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("success"):
        fail("chat probe returned success=false", data)
    text = str(data.get("response") or data.get("content") or "")
    if not text:
        fail("chat returned empty response", data)
    workflow_contract = data.get("workflow_contract") or {}
    pending_task = workflow_contract.get("pending_task") or {}
    if not pending_task.get("task_id"):
        fail("chat probe did not expose pending task workflow contract", data)
    ok("chat interaction works")


def tool_required_probe(client: SessionClient) -> None:
    stage("tool-required probe")
    resp = client.post("/api/chat", json_body={"message": "帮我确认这个接口行为"})
    if resp.status_code != 200:
        fail(f"tool-required status={resp.status_code}", resp.text)
    data = resp.json()
    if not data.get("success"):
        fail("tool-required probe returned success=false", data)
    text = str(data.get("response") or data.get("content") or "")
    if not text:
        fail("tool-required probe returned empty response", data)
    if "[Reached max turns" in text:
        fail("tool-required probe hit max-turn ceiling", data)
    structured = data.get("structured_answer") or {}
    self_model = structured.get("self_model") or {}
    if self_model.get("answer_mode") != "tool_required":
        fail("tool-required probe did not preserve tool_required answer_mode", data)
    if self_model.get("verification_mode") not in {"light", "required", "evidence_required", "tool_required"}:
        fail("tool-required probe returned unexpected verification mode", data)
    ok("tool-required route behaves acceptably under current timeout profile")


def draft_activation_probe(client: SessionClient) -> None:
    stage("draft continuation path")

    continue_data = None
    apply_action = None
    saw_context_view = False
    for index in range(3):
        stage(f"draft continue[{index}]")
        continue_resp = client.post("/api/chat", json_body={"message": "继续"})
        if continue_resp.status_code != 200:
            fail(f"draft continue[{index}] status={continue_resp.status_code}", continue_resp.text)
        continue_data = continue_resp.json()
        if not continue_data.get("success"):
            fail(f"draft continue[{index}] returned success=false", continue_data)
        context_view = continue_data.get("context_view")
        if context_view is None and isinstance(continue_data.get("data"), dict):
            context_view = continue_data["data"].get("context_view")
        context_view = context_view or {}
        if isinstance(context_view, dict) and isinstance(context_view.get("stable"), list):
            saw_context_view = True
        actions = continue_data.get("actions") or []
        for item in actions:
            payload = item.get("payload") or {}
            if payload.get("intent") == "apply_draft_app":
                apply_action = {"action_id": item.get("id"), "action_params": payload}
                break
        if apply_action is not None:
            break

    if continue_data is None:
        fail("draft continuation produced no response")
    if not saw_context_view:
        fail("draft continuation did not expose recent working memory context_view", continue_data)
    if apply_action is None:
        fail("draft continuation did not expose a real apply_draft_app action", continue_data)
    ok("draft continuation exposed activation handoff action and context view")

    stage("restart-bounded continuation recovery")
    recovered_client = SessionClient()
    recovered_client.s.cookies.update(client.s.cookies)
    login(recovered_client)
    recovered_client.session_id = client.session_id
    recovery_resp = recovered_client.get(f"/api/sessions/{client.session_id}/history")
    if recovery_resp.status_code != 200:
        fail(f"bounded continuation recovery status={recovery_resp.status_code}", recovery_resp.text)
    recovery_data = recovery_resp.json()
    if not recovery_data.get("success"):
        fail("bounded continuation recovery returned success=false", recovery_data)
    history = recovery_data.get("history") or []
    if not history:
        fail("bounded continuation recovery missing session history", recovery_data)
    if not any("继续" in str(item.get("content") or "") or "创建一个笔记 app" in str(item.get("content") or "") for item in history):
        fail("bounded continuation recovery did not preserve recent conversation state", recovery_data)
    ok("bounded continuation recovery remains available after client restart")

    stage("draft apply action")
    action_resp = client.post("/api/action", json_body=apply_action)
    if action_resp.status_code != 200:
        fail(f"draft apply action status={action_resp.status_code}", action_resp.text)
    action_data = action_resp.json()
    if not action_data.get("success"):
        fail("draft apply action returned success=false", action_data)
    if not isinstance(action_data.get("data"), dict):
        fail("draft apply action missing structured data payload", action_data)
    if action_data["data"].get("lifecycle_transition") != "draft_to_running_activation":
        fail("draft apply action missing draft_to_running_activation transition", action_data)
    actions = action_data.get("actions") or []
    if not actions:
        fail("draft apply action missing follow-up actions", action_data)
    first_payload = (actions[0] or {}).get("payload") or {}
    if first_payload.get("intent") != "query_app":
        fail("draft apply action did not expose query_app follow-up", action_data)
    ok("draft HTTP action activation surface works")


def run_self_iteration_cycle(client: SessionClient) -> dict[str, Any]:
    stage("governance self-iteration cycle")
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
    ok("governance self-iteration cycle triggered")
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
    stage("fetch latest regression")
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
    start_server_if_needed()
    client = SessionClient()
    login(client)
    ensure_schedule(client)
    chat_probe(client)
    tool_required_probe(client)
    draft_activation_probe(client)
    result = run_self_iteration_cycle(client)
    verify_cycle_payload(result)
    fetch_latest_regression(client)
    print(f"{GREEN}SELF-ITERATION SERVICE-UP E2E PASSED{NC}")


if __name__ == "__main__":
    main()
