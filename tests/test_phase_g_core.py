"""Tests for Phase G core infrastructure."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.skill_worker import SkillWorker, WorkerHealth
from app.core.message_bus import MessageBus, WorkerNotFoundError, RpcTimeoutError
from app.core.worker_manager import WorkerManager
from app.core.model_health import ModelHealthStatus
from app.services.path_store import PathStore, PathTemplate, PathStep


# -- SkillWorker --------------------------------------------------------------

@pytest.fixture
def sample_worker():
    class TestWorker(SkillWorker):
        worker_id = "test.worker"
        async def init(self, config=None): pass
        async def process(self, request): return {"result": "ok"}
        async def shutdown(self): pass
    return TestWorker()


# -- MessageBus ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_bus_rpc_success():
    bus = MessageBus()
    queue: asyncio.Queue = asyncio.Queue()
    bus.register_worker("test.skill", queue)

    # Simulate worker processing
    async def worker_loop():
        request = await queue.get()
        await bus.deliver_response(request.request_id, {"status": "completed", "output": {"data": 42}})

    asyncio.create_task(worker_loop())
    result = await bus.rpc("test.skill", {"query": "hello"}, timeout=5.0)
    assert result["output"]["data"] == 42


@pytest.mark.asyncio
async def test_bus_rpc_worker_not_found():
    bus = MessageBus()
    with pytest.raises(WorkerNotFoundError):
        await bus.rpc("nonexistent.skill", {})


@pytest.mark.asyncio
async def test_bus_rpc_timeout():
    bus = MessageBus()
    queue: asyncio.Queue = asyncio.Queue()
    bus.register_worker("slow.skill", queue)

    with pytest.raises(RpcTimeoutError):
        await bus.rpc("slow.skill", {}, timeout=0.1)


# -- PathStore ----------------------------------------------------------------

@pytest.fixture
def tmp_paths_dir(tmp_path):
    return str(tmp_path / "paths")


def test_path_store_save_and_load(tmp_paths_dir):
    store = PathStore(paths_dir=tmp_paths_dir)
    path = PathTemplate(
        path_id="path.test",
        name="Test Path",
        description="A test",
        steps=[
            PathStep(name="step1", skill="skill.a", action="analyze"),
            PathStep(name="step2", skill="skill.b", on_failure="skip"),
        ],
    )
    store.save(path)

    # Reload
    store2 = PathStore(paths_dir=tmp_paths_dir)
    loaded = store2.load_all()
    assert "path.test" in loaded
    assert loaded["path.test"].name == "Test Path"
    assert len(loaded["path.test"].steps) == 2
    assert loaded["path.test"].steps[1].on_failure == "skip"


def test_path_store_offline_paths(tmp_paths_dir):
    store = PathStore(paths_dir=tmp_paths_dir)
    store.save(PathTemplate(path_id="path.online", name="Online", steps=[]))
    store.save(PathTemplate(path_id="path.offline", name="Offline", offline_capable=True, steps=[]))

    store.load_all()
    assert len(store.list_offline_paths()) == 1
    assert len(store.list_online_paths()) == 1


# -- WorkerManager ------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_manager_lifecycle(sample_worker):
    bus = MessageBus()
    manager = WorkerManager(bus)

    await manager.register_and_start(sample_worker)
    assert manager.is_healthy("test.worker")
    assert "test.worker" in manager.list_workers()

    await manager.shutdown_all()
    assert not manager.is_healthy("test.worker")
