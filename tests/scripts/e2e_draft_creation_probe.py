#!/usr/bin/env python3
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
USERNAME = "e2e-draft-probe"
PROJECT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DATA_DIR = Path(os.environ.get("AGENTSYSTEM_DATA_DIR", str(PROJECT_DIR / "data"))).expanduser().resolve()
SERVER_LOG = RUNTIME_DATA_DIR / "e2e_draft_probe.log"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

_SERVER_PROCESS: subprocess.Popen[str] | None = None
_SERVER_LOG_HANDLE = None


def say(kind: str, msg: str) -> None:
    color = {"OK": GREEN, "FAIL": RED, "STAGE": YELLOW}.get(kind, NC)
    print(f"{color}{kind}{NC}: {msg}")
    sys.stdout.flush()


def fail(msg: str, payload: Any | None = None) -> None:
    say("FAIL", msg)
    if payload is not None:
        try:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            print(payload)
    sys.exit(1)


def cleanup_server() -> None:
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


def kill_port() -> None:
    subprocess.run("fuser -k 8765/tcp >/dev/null 2>&1 || true", shell=True, check=False)


def ensure_server_ready(timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/api/status", timeout=3)
            if response.status_code == 200:
                say("OK", "server is ready")
                return
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    fail("server did not become ready in time", str(last_error) if last_error else None)


def start_server() -> None:
    global _SERVER_PROCESS, _SERVER_LOG_HANDLE
    kill_port()
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    _SERVER_LOG_HANDLE = SERVER_LOG.open("w", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(PROJECT_DIR), "AGENTSYSTEM_DATA_DIR": str(RUNTIME_DATA_DIR)}
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
        cwd=str(RUNTIME_DATA_DIR),
        stdout=_SERVER_LOG_HANDLE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    atexit.register(cleanup_server)
    ensure_server_ready()


def post_json(session: requests.Session, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = session.post(f"{BASE_URL}{path}", json=payload, timeout=120)
    try:
        data = response.json()
    except Exception:
        fail(f"{path} returned non-json status={response.status_code}", response.text)
    if response.status_code != 200:
        fail(f"{path} returned status={response.status_code}", data)
    return data


def main() -> None:
    say("STAGE", f"BASE_URL={BASE_URL}")
    start_server()
    s = requests.Session()

    say("STAGE", "login")
    login_data = post_json(s, "/login", {"username": USERNAME, "password": "ignored"})
    if not login_data.get("success"):
        fail("login returned success=false", login_data)
    say("OK", "login")

    say("STAGE", "draft creation")
    create_data = post_json(s, "/api/chat", {"message": "创建一个笔记 app"})
    print(json.dumps({"draft_creation": create_data}, ensure_ascii=False, indent=2))
    if not create_data.get("success"):
        fail("draft creation returned success=false", create_data)
    say("OK", "draft creation")

    say("STAGE", "first continue")
    continue_data = post_json(s, "/api/chat", {"message": "继续"})
    print(json.dumps({"first_continue": continue_data}, ensure_ascii=False, indent=2))
    if not continue_data.get("success"):
        fail("first continue returned success=false", continue_data)
    say("OK", "first continue")

    say("OK", "focused draft probe passed")


if __name__ == "__main__":
    main()
