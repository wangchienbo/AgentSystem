"""App Bootstrap — App 进程启动入口。

用法:
    python3 -m app.runtime.app_bootstrap --app-id <instance_id> --data-dir <path>

启动后自动:
1. 向 RuntimeCenter 自注册
2. 开始发送心跳
3. 等待主进程指令
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_app_bootstrap(
    app_instance_id: str,
    data_dir: str = "data",
    heartbeat_interval: int = 30,
) -> None:
    """Run the app bootstrap: self-register + heartbeat loop."""
    data_path = Path(data_dir)
    runtime_file = data_path / "runtime_center.json"

    # Self-register by writing to runtime_center.json
    entry = {
        "asset_id": app_instance_id,
        "version": os.environ.get("APP_VERSION", "0.0.0"),
        "pid": os.getpid(),
        "endpoint": os.environ.get("APP_ENDPOINT", f"http://127.0.0.1:0"),
        "owner": os.environ.get("APP_OWNER", "system"),
        "status": "running",
        "started_at": _now_iso(),
        "last_heartbeat": _now_iso(),
    }

    # Write registration
    runtime_data: dict = {}
    if runtime_file.exists():
        try:
            runtime_data = json.loads(runtime_file.read_text())
        except Exception:
            pass

    runtime_data[app_instance_id] = entry
    runtime_file.write_text(json.dumps(runtime_data, ensure_ascii=False, indent=2))

    logger.info(
        "App %s self-registered: pid=%d, version=%s",
        app_instance_id, os.getpid(), entry["version"],
    )

    # Heartbeat loop
    def _handle_signal(signum, frame):
        entry["status"] = "stopped"
        runtime_data[app_instance_id] = entry
        runtime_file.write_text(json.dumps(runtime_data, ensure_ascii=False, indent=2))
        logger.info("App %s stopped by signal", app_instance_id)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("App %s heartbeat loop started (interval=%ds)", app_instance_id, heartbeat_interval)

    try:
        while True:
            entry["last_heartbeat"] = _now_iso()
            runtime_data[app_instance_id] = entry
            runtime_file.write_text(json.dumps(runtime_data, ensure_ascii=False, indent=2))
            time.sleep(heartbeat_interval)
    except (KeyboardInterrupt, SystemExit):
        _handle_signal(signal.SIGTERM, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="App process bootstrap")
    parser.add_argument("--app-id", required=True, help="App instance ID")
    parser.add_argument("--data-dir", default="data", help="Data directory path")
    parser.add_argument("--heartbeat-interval", type=int, default=30, help="Heartbeat interval in seconds")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run_app_bootstrap(
        app_instance_id=args.app_id,
        data_dir=args.data_dir,
        heartbeat_interval=args.heartbeat_interval,
    )
