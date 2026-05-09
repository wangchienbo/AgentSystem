"""App Process Manager — 每个 App 作为独立子进程运行。

职责:
1. 启动 App 子进程（subprocess.Popen）
2. 管理子进程生命周期（start/stop/restart）
3. 心跳监控 + 崩溃检测
4. 进程间通信（JSON over stdin/stdout）

设计原则:
- 子进程完全隔离，崩溃不影响主进程
- 父进程只管理生命周期，不干涉业务逻辑
- 通信协议最小化：JSON 请求/响应
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AppProcessInfo:
    """Running app process info."""
    app_instance_id: str
    pid: int
    status: str  # running | stopped | crashed | starting
    started_at: str
    endpoint: str = ""
    last_heartbeat: str = ""
    crash_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AppProcessManager:
    """Manages app subprocess lifecycle."""

    def __init__(
        self,
        runtime_center: Any = None,
        data_dir: str = "data",
    ) -> None:
        self._runtime_center = runtime_center
        self._data_dir = Path(data_dir)
        self._processes: dict[str, AppProcessInfo] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()
        self._heartbeat_interval = 30  # seconds
        self._heartbeat_timeout = 90   # seconds

    def start_app_process(
        self,
        app_instance_id: str,
        entry_point: str,
        version: str = "0.0.0",
        owner: str = "system",
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> AppProcessInfo:
        """Start an app as a subprocess. Returns process info."""
        with self._lock:
            existing = self._processes.get(app_instance_id)
            if existing and existing.status == "running":
                return existing

        cmd = entry_point if isinstance(entry_point, list) else shlex.split(entry_point)
        full_env = {**os.environ}
        full_env["APP_INSTANCE_ID"] = app_instance_id
        full_env["APP_VERSION"] = version
        full_env["AGENTSYSTEM_DATA_DIR"] = str(self._data_dir)
        if env:
            full_env.update(env)

        work_dir = str((Path(cwd).expanduser() if cwd else self._data_dir).resolve())

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=full_env,
                cwd=work_dir,
                start_new_session=True,
                text=True,
            )
        except Exception as e:
            logger.error("Failed to start app process %s: %s", app_instance_id, e)
            with self._lock:
                self._processes[app_instance_id] = AppProcessInfo(
                    app_instance_id=app_instance_id,
                    pid=0,
                    status="crashed",
                    started_at=self._now_iso(),
                    crash_count=(existing.crash_count + 1) if existing else 1,
                )
            raise

        now = self._now_iso()
        info = AppProcessInfo(
            app_instance_id=app_instance_id,
            pid=proc.pid,
            status="running",
            started_at=now,
            endpoint=f"http://127.0.0.1:0",
            last_heartbeat=now,
        )

        with self._lock:
            self._processes[app_instance_id] = info
            self._procs[app_instance_id] = proc

        # Register in RuntimeCenter
        if self._runtime_center:
            self._runtime_center.register(
                asset_id=app_instance_id,
                version=version,
                pid=proc.pid,
                endpoint=info.endpoint,
                owner=owner,
            )

        logger.info("App process started: %s pid=%d", app_instance_id, proc.pid)
        return info

    def stop_app_process(self, app_instance_id: str, timeout: float = 5.0) -> bool:
        """Stop an app subprocess. Graceful SIGTERM then SIGKILL."""
        with self._lock:
            proc = self._procs.get(app_instance_id)
            info = self._processes.get(app_instance_id)

        if proc is None and info is None:
            return False

        if proc:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            except Exception as e:
                logger.warning("Error stopping process %s: %s", app_instance_id, e)

        with self._lock:
            self._procs.pop(app_instance_id, None)
            if info:
                info.status = "stopped"

        if self._runtime_center:
            self._runtime_center.mark_stopped(app_instance_id)
            self._runtime_center.unregister(app_instance_id)

        logger.info("App process stopped: %s", app_instance_id)
        return True

    def check_health(self, app_instance_id: str) -> dict[str, Any]:
        """Check if an app process is alive and healthy."""
        with self._lock:
            proc = self._procs.get(app_instance_id)
            info = self._processes.get(app_instance_id)

        if info is None:
            return {"status": "not_found", "app_instance_id": app_instance_id}

        process_alive = False
        if proc:
            rc = proc.poll()
            process_alive = rc is None
            if not process_alive:
                # Process exited
                with self._lock:
                    info.status = "crashed"
                    info.crash_count += 1
                if self._runtime_center:
                    self._runtime_center.mark_crashed(app_instance_id)

        # Check heartbeat timeout
        heartbeat_ok = True
        if info.last_heartbeat:
            try:
                last_hb = datetime.fromisoformat(info.last_heartbeat)
                elapsed = (datetime.now(timezone.utc) - last_hb).total_seconds()
                if elapsed > self._heartbeat_timeout:
                    heartbeat_ok = False
            except Exception:
                pass

        status = "running" if (process_alive and heartbeat_ok) else (
            "crashed" if not process_alive else "heartbeat_timeout"
        )

        return {
            "status": status,
            "app_instance_id": app_instance_id,
            "pid": info.pid,
            "process_alive": process_alive,
            "heartbeat_ok": heartbeat_ok,
            "crash_count": info.crash_count,
            "started_at": info.started_at,
            "last_heartbeat": info.last_heartbeat,
        }

    def heartbeat(self, app_instance_id: str) -> bool:
        """Record a heartbeat from an app process."""
        with self._lock:
            info = self._processes.get(app_instance_id)
            if info is None:
                return False
            info.last_heartbeat = self._now_iso()

        if self._runtime_center:
            entry = self._runtime_center.get(app_instance_id)
            if entry:
                self._runtime_center.heartbeat(app_instance_id, entry.pid)

        return True

    def list_processes(self) -> list[dict[str, Any]]:
        """List all managed app processes."""
        with self._lock:
            return [info.to_dict() for info in self._processes.values()]

    def get_process(self, app_instance_id: str) -> AppProcessInfo | None:
        with self._lock:
            return self._processes.get(app_instance_id)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
