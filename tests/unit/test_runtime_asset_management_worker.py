from __future__ import annotations

import subprocess
import time

from app.models.app_instance import AppInstance
from app.system.catalog.runtime_center import RuntimeCenter
from app.system.runtime.lifecycle import AppLifecycleService
from app.system.workers.app_mgmt import AppManagementWorker


def _make_running_instance(app_id: str = "novel") -> AppInstance:
    return AppInstance(
        id=app_id,
        blueprint_id="app.novel",
        owner_user_id="wangchienbo",
        status="installed",
        installed_version="1.2.0",
        data_namespace=f"ns.{app_id}",
    )


def test_app_management_worker_start_and_health_check_asset(tmp_path) -> None:
    lifecycle = AppLifecycleService()
    lifecycle.register_instance(_make_running_instance())
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime_center.json"))
    worker = AppManagementWorker(lifecycle=lifecycle, runtime_center=runtime_center)

    # Start a real subprocess so health check can verify it's alive
    proc = subprocess.Popen(["python3", "-c", "import time; time.sleep(100)"])
    try:
        started = worker.execute("start_asset", "novel", {"pid": proc.pid, "endpoint": "http://localhost:8001"})
        assert started["status"] == "success"
        assert started["data"]["status"] == "running"

        health = worker.execute("health_check_asset", "novel", {})
        assert health["status"] == "success"
        assert health["data"]["asset_id"] == "novel"
        assert health["data"]["pid"] == proc.pid
    finally:
        proc.terminate()
        proc.wait()


def test_app_management_worker_stop_asset(tmp_path) -> None:
    lifecycle = AppLifecycleService()
    lifecycle.register_instance(_make_running_instance())
    runtime_center = RuntimeCenter(data_file=str(tmp_path / "runtime_center.json"))
    worker = AppManagementWorker(lifecycle=lifecycle, runtime_center=runtime_center)

    proc = subprocess.Popen(["python3", "-c", "import time; time.sleep(100)"])
    try:
        worker.execute("start_asset", "novel", {"pid": proc.pid})
        stopped = worker.execute("stop_asset", "novel", {})
        assert stopped["status"] == "success"
        assert runtime_center.get("novel") is None
    finally:
        proc.terminate()
        proc.wait()
