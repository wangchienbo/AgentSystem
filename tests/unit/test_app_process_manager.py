"""Unit tests for AppProcessManager."""
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


@pytest.fixture
def tmp_data(tmp_path):
    return str(tmp_path)


@pytest.fixture
def manager(tmp_data):
    return AppProcessManager(data_dir=tmp_data)


def test_start_app_process(manager):
    info = manager.start_app_process(
        app_instance_id="test.app.v1",
        entry_point="python3 -c \"import time; time.sleep(100)\"",
        version="0.1.0",
    )
    assert info.status == "running"
    assert info.pid > 0
    assert manager.get_process("test.app.v1") is not None


def test_stop_app_process(manager):
    info = manager.start_app_process(
        app_instance_id="test.stop",
        entry_point="python3 -c \"import time; time.sleep(100)\"",
    )
    assert info.status == "running"
    result = manager.stop_app_process("test.stop")
    assert result is True
    assert manager.get_process("test.stop").status == "stopped"


def test_health_check_alive(manager):
    info = manager.start_app_process(
        app_instance_id="test.health",
        entry_point="python3 -c \"import time; time.sleep(100)\"",
    )
    health = manager.check_health("test.health")
    assert health["status"] == "running"
    assert health["process_alive"] is True


def test_health_check_crashed(manager):
    info = manager.start_app_process(
        app_instance_id="test.crash",
        entry_point="python3 -c \"exit(1)\"",
    )
    # Give it time to crash
    time.sleep(1)
    health = manager.check_health("test.crash")
    assert health["status"] == "crashed"
    assert health["crash_count"] >= 1


def test_heartbeat(manager):
    manager.start_app_process(
        app_instance_id="test.hb",
        entry_point="python3 -c \"import time; time.sleep(100)\"",
    )
    assert manager.heartbeat("test.hb") is True
    assert manager.heartbeat("nonexistent") is False


def test_list_processes(manager):
    manager.start_app_process("test.a", entry_point="python3 -c \"import time; time.sleep(100)\"")
    manager.start_app_process("test.b", entry_point="python3 -c \"import time; time.sleep(100)\"")
    procs = manager.list_processes()
    assert len(procs) == 2


def test_not_found(manager):
    assert manager.get_process("nonexistent") is None
    health = manager.check_health("nonexistent")
    assert health["status"] == "not_found"
