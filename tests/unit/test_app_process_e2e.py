"""E2E tests for App process isolation."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

# Ensure project root is on path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.system.runtime.app_process_manager import AppProcessManager


class TestAppProcessE2E:
    """End-to-end tests for App subprocess isolation."""

    def test_start_query_stop_lifecycle(self, tmp_path):
        """Full lifecycle: start → query status → stop → verify cleanup."""
        mgr = AppProcessManager(data_dir=str(tmp_path))

        # Start
        info = mgr.start_app_process(
            app_instance_id="e2e.app.v1",
            entry_point="python3 -c \"import time; time.sleep(100)\"",
            version="1.0.0",
            owner="test-user",
        )
        assert info.status == "running"
        assert info.pid > 0

        # Query status
        health = mgr.check_health("e2e.app.v1")
        assert health["status"] == "running"
        assert health["process_alive"] is True
        assert health["pid"] == info.pid

        # Stop
        result = mgr.stop_app_process("e2e.app.v1")
        assert result is True

        # Verify stopped
        stopped_info = mgr.get_process("e2e.app.v1")
        assert stopped_info.status == "stopped"

        # Health after stop should show crashed or not_found-like
        health2 = mgr.check_health("e2e.app.v1")
        assert health2["status"] in ("crashed", "not_found")

    def test_crash_detection(self, tmp_path):
        """App that crashes should be detected as crashed."""
        mgr = AppProcessManager(data_dir=str(tmp_path))

        info = mgr.start_app_process(
            app_instance_id="e2e.crash",
            entry_point="python3 -c \"import sys; sys.exit(1)\"",
        )

        # Wait for crash
        time.sleep(1.5)

        health = mgr.check_health("e2e.crash")
        assert health["status"] == "crashed"
        assert health["crash_count"] >= 1
        assert health["process_alive"] is False

    def test_multiple_isolated_apps(self, tmp_path):
        """Multiple apps run in isolated processes; crashing one doesn't affect others."""
        mgr = AppProcessManager(data_dir=str(tmp_path))

        # Start two apps
        mgr.start_app_process("e2e.app.a", entry_point="python3 -c \"import time; time.sleep(100)\"")
        mgr.start_app_process("e2e.app.b", entry_point="python3 -c \"import time; time.sleep(100)\"")

        # Both running
        assert mgr.get_process("e2e.app.a").status == "running"
        assert mgr.get_process("e2e.app.b").status == "running"

        # Crash one
        mgr.start_app_process("e2e.app.c", entry_point="python3 -c \"import sys; sys.exit(1)\"")
        time.sleep(1.5)

        # A should still be running despite C crashing
        health_a = mgr.check_health("e2e.app.a")
        assert health_a["status"] == "running"

        health_c = mgr.check_health("e2e.app.c")
        assert health_c["status"] == "crashed"

        # Cleanup
        mgr.stop_app_process("e2e.app.a")
        mgr.stop_app_process("e2e.app.b")

    def test_heartbeat_updates(self, tmp_path):
        """Heartbeat should update last_heartbeat timestamp."""
        mgr = AppProcessManager(data_dir=str(tmp_path))
        mgr.start_app_process("e2e.hb", entry_point="python3 -c \"import time; time.sleep(100)\"")

        first_hb = mgr.get_process("e2e.hb").last_heartbeat
        time.sleep(0.5)
        mgr.heartbeat("e2e.hb")
        second_hb = mgr.get_process("e2e.hb").last_heartbeat

        assert second_hb >= first_hb

        mgr.stop_app_process("e2e.hb")

    def test_list_processes(self, tmp_path):
        """List should show all running processes."""
        mgr = AppProcessManager(data_dir=str(tmp_path))
        mgr.start_app_process("e2e.list.a", entry_point="python3 -c \"import time; time.sleep(100)\"")
        mgr.start_app_process("e2e.list.b", entry_point="python3 -c \"import time; time.sleep(100)\"")

        procs = mgr.list_processes()
        assert len(procs) == 2

        mgr.stop_app_process("e2e.list.a")
        mgr.stop_app_process("e2e.list.b")
