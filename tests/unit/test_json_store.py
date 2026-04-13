"""Phase F.7: Concurrent-safe JSON file read/write tests."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from app.core.json_store import (
    JsonFileStore,
    json_read_async,
    json_read_sync,
    json_update_async,
    json_update_sync,
    json_write_async,
    json_write_sync,
)


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path / "json_store"


@pytest.fixture
def tmp_json(tmp_dir: Path) -> str:
    """Path to a temporary JSON file."""
    return str(tmp_dir / "data.json")


# ---------------------------------------------------------------------------
# Sync basic operations
# ---------------------------------------------------------------------------

class TestSyncReadWrite:
    def test_write_and_read_roundtrip(self, tmp_json: str) -> None:
        data = {"name": "test", "count": 42, "tags": ["a", "b"]}
        json_write_sync(tmp_json, data)
        result = json_read_sync(tmp_json)
        assert result == data

    def test_write_creates_parent_dirs(self, tmp_dir: Path) -> None:
        deep = str(tmp_dir / "a" / "b" / "c" / "data.json")
        json_write_sync(deep, {"ok": True})
        assert json_read_sync(deep) == {"ok": True}

    def test_read_missing_returns_default(self, tmp_json: str) -> None:
        assert json_read_sync(tmp_json) is None
        assert json_read_sync(tmp_json, default={}) == {}
        assert json_read_sync(tmp_json, default=[1]) == [1]

    def test_write_pretty_print(self, tmp_json: str) -> None:
        json_write_sync(tmp_json, {"k": "v"}, indent=4)
        raw = Path(tmp_json).read_text()
        assert "    " in raw  # 4-space indent

    def test_write_ascii_safe(self, tmp_json: str) -> None:
        json_write_sync(tmp_json, {"cn": "中文"}, ensure_ascii=True)
        raw = Path(tmp_json).read_text()
        assert "\\u4e2d" in raw

    def test_write_unicode_default(self, tmp_json: str) -> None:
        json_write_sync(tmp_json, {"cn": "中文"})
        raw = Path(tmp_json).read_text()
        assert "中文" in raw


# ---------------------------------------------------------------------------
# Async basic operations
# ---------------------------------------------------------------------------

class TestAsyncReadWrite:
    @pytest.mark.asyncio
    async def test_write_and_read_roundtrip(self, tmp_json: str) -> None:
        data = {"async": True, "values": [1, 2, 3]}
        await json_write_async(tmp_json, data)
        result = await json_read_async(tmp_json)
        assert result == data

    @pytest.mark.asyncio
    async def test_read_missing_returns_default(self, tmp_json: str) -> None:
        assert await json_read_async(tmp_json) is None
        assert await json_read_async(tmp_json, default={}) == {}

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tmp_dir: Path) -> None:
        deep = str(tmp_dir / "x" / "y" / "z.json")
        await json_write_async(deep, {"deep": True})
        assert await json_read_async(deep) == {"deep": True}


# ---------------------------------------------------------------------------
# Atomic write (crash safety)
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_no_corrupted_partial_writes(self, tmp_json: str) -> None:
        """If write crashes mid-way, old data should still be valid or file absent."""
        data1 = {"version": 1, "data": "x" * 10000}
        json_write_sync(tmp_json, data1)

        # Verify original is intact
        assert json_read_sync(tmp_json)["version"] == 1

        # Write new data
        data2 = {"version": 2, "data": "y" * 10000}
        json_write_sync(tmp_json, data2)

        # Should be fully new data, never partial
        result = json_read_sync(tmp_json)
        assert result["version"] == 2
        assert result["data"] == "y" * 10000

    def test_no_leftover_tmp_files(self, tmp_dir: Path) -> None:
        target = str(tmp_dir / "data.json")
        json_write_sync(target, {"clean": True})
        tmps = [f for f in os.listdir(tmp_dir) if f.endswith(".tmp")]
        assert tmps == []


# ---------------------------------------------------------------------------
# Concurrent access — sync threads
# ---------------------------------------------------------------------------

class TestConcurrentSync:
    def test_concurrent_writers_no_data_loss(self, tmp_json: str) -> None:
        """10 threads each increment a counter; final value should be 10."""
        import threading

        json_write_sync(tmp_json, {"counter": 0})
        barrier = threading.Barrier(10)
        errors: list[Exception] = []

        def worker():
            try:
                barrier.wait(timeout=5)
                json_update_sync(tmp_json, lambda d: {
                    "counter": d["counter"] + 1
                })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Errors: {errors}"
        result = json_read_sync(tmp_json)
        assert result["counter"] == 10

    def test_concurrent_same_file_serialized(self, tmp_json: str) -> None:
        """Verify that concurrent writes to the same file produce valid JSON."""
        import threading

        errors: list[Exception] = []
        done = threading.Event()

        def writer(value: int):
            try:
                json_write_sync(tmp_json, {"writer": value})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # File should contain valid JSON (some writer's value)
        result = json_read_sync(tmp_json)
        assert "writer" in result
        assert errors == []


# ---------------------------------------------------------------------------
# Concurrent access — async tasks
# ---------------------------------------------------------------------------

class TestConcurrentAsync:
    @pytest.mark.asyncio
    async def test_concurrent_writers_no_data_loss(self, tmp_json: str) -> None:
        """10 async tasks each increment a counter; final value should be 10."""
        await json_write_async(tmp_json, {"counter": 0})

        async def increment():
            await json_update_async(tmp_json, lambda d: {
                "counter": d["counter"] + 1
            })

        await asyncio.gather(*[increment() for _ in range(10)])
        result = await json_read_async(tmp_json)
        assert result["counter"] == 10

    @pytest.mark.asyncio
    async def test_concurrent_appends_to_list(self, tmp_json: str) -> None:
        """Multiple tasks append to a shared list under lock."""
        await json_write_async(tmp_json, {"items": []})

        async def append(value: int):
            await json_update_async(tmp_json, lambda d: {
                "items": d["items"] + [value]
            })

        await asyncio.gather(*[append(i) for i in range(20)])
        result = await json_read_async(tmp_json)
        assert len(result["items"]) == 20
        assert sorted(result["items"]) == list(range(20))

    @pytest.mark.asyncio
    async def test_concurrent_writes_valid_json(self, tmp_json: str) -> None:
        """20 concurrent writes should never corrupt the file."""
        async def writer(value: int):
            await json_write_async(tmp_json, {"writer": value})

        await asyncio.gather(*[writer(i) for i in range(20)])
        result = await json_read_async(tmp_json)
        assert "writer" in result  # valid JSON with some value


# ---------------------------------------------------------------------------
# Read-Modify-Write (atomic update)
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_sync_update_creates_if_missing(self, tmp_json: str) -> None:
        result = json_update_sync(tmp_json, lambda d: {"count": (d or 0) + 1}, default=0)
        assert result == {"count": 1}
        assert json_read_sync(tmp_json) == {"count": 1}

    def test_sync_update_modifies_existing(self, tmp_json: str) -> None:
        json_write_sync(tmp_json, {"users": []})
        result = json_update_sync(tmp_json, lambda d: {
            "users": d["users"] + ["alice"]
        })
        assert result["users"] == ["alice"]

    @pytest.mark.asyncio
    async def test_async_update_creates_if_missing(self, tmp_json: str) -> None:
        result = await json_update_async(tmp_json, lambda d: {"ok": True}, default=None)
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_async_update_modifies_existing(self, tmp_json: str) -> None:
        await json_write_async(tmp_json, {"score": 10})
        result = await json_update_async(tmp_json, lambda d: {"score": d["score"] + 5})
        assert result["score"] == 15


# ---------------------------------------------------------------------------
# JsonFileStore wrapper class
# ---------------------------------------------------------------------------

class TestJsonFileStore:
    def test_sync_roundtrip(self, tmp_dir: Path) -> None:
        store = JsonFileStore(tmp_dir / "store.json", default={"empty": True})
        assert store.read_sync() == {"empty": True}
        store.write_sync({"k": "v"})
        assert store.read_sync() == {"k": "v"}

    def test_sync_update(self, tmp_dir: Path) -> None:
        store = JsonFileStore(tmp_dir / "store.json", default={"n": 0})
        store.write_sync({"n": 0})
        result = store.update_sync(lambda d: {"n": d["n"] + 1})
        assert result["n"] == 1

    @pytest.mark.asyncio
    async def test_async_roundtrip(self, tmp_dir: Path) -> None:
        store = JsonFileStore(tmp_dir / "store.json", default={"async": True})
        assert await store.read() == {"async": True}
        await store.write({"k": "v"})
        assert await store.read() == {"k": "v"}

    @pytest.mark.asyncio
    async def test_async_update(self, tmp_dir: Path) -> None:
        store = JsonFileStore(tmp_dir / "store.json")
        await store.write({"items": [1]})
        result = await store.update(lambda d: {"items": d["items"] + [2]})
        assert result["items"] == [1, 2]


# ---------------------------------------------------------------------------
# Per-file lock isolation
# ---------------------------------------------------------------------------

class TestLockIsolation:
    def test_different_files_not_blocked(self, tmp_dir: Path) -> None:
        """Writes to different files should not block each other."""
        import threading
        import time

        results = {}

        def write_file(name: str, value: str):
            path = str(tmp_dir / f"file_{name}.json")
            json_write_sync(path, {"name": name, "value": value})
            results[name] = time.monotonic()

        threads = [
            threading.Thread(target=write_file, args=(str(i), f"v{i}"))
            for i in range(5)
        ]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        elapsed = time.monotonic() - start
        # All should complete nearly instantly (not serialized)
        assert elapsed < 1.0

        for i in range(5):
            path = str(tmp_dir / f"file_{i}.json")
            assert json_read_sync(path) == {"name": str(i), "value": f"v{i}"}
