"""App Process IPC — 父进程与子进程间 JSON 通信。

协议:
- 父进程 → 子进程: JSON 行写入 stdin
- 子进程 → 父进程: JSON 行写入 stdout
- 格式: {"request_id": "...", "action": "...", "payload": {...}}
- 响应: {"request_id": "...", "status": "ok"|"error", "result": {...}|{"error": "..."}}
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IPCMessage:
    request_id: str
    status: str  # ok | error
    action: str = ""
    result: dict | None = None
    error: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "request_id": self.request_id,
            "status": self.status,
            "action": self.action,
            "result": self.result,
            "error": self.error,
        })

    @classmethod
    def from_json(cls, text: str) -> "IPCMessage":
        data = json.loads(text.strip())
        return cls(
            request_id=data.get("request_id", ""),
            status=data.get("status", "error"),
            action=data.get("action", ""),
            result=data.get("result"),
            error=data.get("error", ""),
        )


class AppProcessIPC:
    """Manages JSON IPC with a subprocess."""

    def __init__(self, proc: subprocess.Popen, timeout: float = 30.0) -> None:
        self._proc = proc
        self._timeout = timeout
        self._lock = threading.Lock()
        self._responses: dict[str, IPCMessage] = {}
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        """Continuously read stdout for JSON responses."""
        assert self._proc.stdout is not None
        while self._proc.poll() is None:
            try:
                line = self._proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8").strip()
                if line_str.startswith("{"):
                    msg = IPCMessage.from_json(line_str)
                    with self._lock:
                        self._responses[msg.request_id] = msg
            except Exception as e:
                logger.warning("IPC read error: %s", e)
                break

    def send(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> IPCMessage | None:
        """Send a request to the subprocess and wait for response."""
        import uuid
        rid = request_id or str(uuid.uuid4())
        msg = IPCMessage(request_id=rid, status="ok", action=action, result=payload or {})

        with self._lock:
            try:
                assert self._proc.stdin is not None
                self._proc.stdin.write(msg.to_json() + "\n")
                self._proc.stdin.flush()
            except Exception as e:
                return IPCMessage(request_id=rid, status="error", error=str(e))

        # Wait for response
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            with self._lock:
                response = self._responses.pop(rid, None)
            if response:
                return response
            time.sleep(0.1)

        return IPCMessage(request_id=rid, status="error", error="timeout")

    def close(self) -> None:
        """Close the IPC channel."""
        if self._proc.stdin:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
