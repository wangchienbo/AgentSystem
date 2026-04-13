"""
Concurrent-safe JSON file storage (Phase F.7).

Provides thread-safe and async-safe read/write with:
- Per-file locking (no global contention)
- Atomic writes (write to .tmp, then os.replace)
- Automatic directory creation
- Corruption prevention on crash
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Per-file lock registries
# ---------------------------------------------------------------------------

# Async locks (for coroutine access)
_async_locks: dict[str, asyncio.Lock] = {}
_async_locks_guard = threading.Lock()  # protects _async_locks dict itself

# Threading locks (for sync access)
_sync_locks: dict[str, threading.Lock] = {}
_sync_locks_guard = threading.Lock()


def _get_async_lock(path: str) -> asyncio.Lock:
    with _async_locks_guard:
        if path not in _async_locks:
            _async_locks[path] = asyncio.Lock()
        return _async_locks[path]


def _get_sync_lock(path: str) -> threading.Lock:
    with _sync_locks_guard:
        if path not in _sync_locks:
            _sync_locks[path] = threading.Lock()
        return _sync_locks[path]


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------

def _atomic_write_sync(path: Path, content: str) -> None:
    """Write content to path atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dir_name = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_name), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


async def _atomic_write_async(path: Path, content: str) -> None:
    """Async wrapper around atomic write (runs sync in executor)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _atomic_write_sync, path, content)


# ---------------------------------------------------------------------------
# Public API: Async
# ---------------------------------------------------------------------------

async def json_read_async(path: str | Path, default: T = None) -> T | Any:
    """Read JSON file with per-file async lock. Returns default if not found."""
    p = Path(path)
    lock = _get_async_lock(str(p.resolve()))
    async with lock:
        if not p.exists():
            return default
        raw = await asyncio.get_running_loop().run_in_executor(
            None, p.read_text, "utf-8"
        )
        return json.loads(raw)


async def json_write_async(path: str | Path, data: Any, *, indent: int = 2, ensure_ascii: bool = False) -> None:
    """Atomically write JSON with per-file async lock."""
    p = Path(path)
    lock = _get_async_lock(str(p.resolve()))
    async with lock:
        content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
        await _atomic_write_async(p, content)


async def json_update_async(
    path: str | Path,
    updater: callable,
    *,
    default: Any = None,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> Any:
    """Read-Modify-Write under a single lock.

    updater: (current_data) -> new_data
    Returns the new_data after write.
    """
    p = Path(path)
    lock = _get_async_lock(str(p.resolve()))
    async with lock:
        if p.exists():
            raw = await asyncio.get_running_loop().run_in_executor(
                None, p.read_text, "utf-8"
            )
            current = json.loads(raw)
        else:
            current = default
        new_data = updater(current)
        content = json.dumps(new_data, indent=indent, ensure_ascii=ensure_ascii)
        await _atomic_write_async(p, content)
        return new_data


# ---------------------------------------------------------------------------
# Public API: Sync
# ---------------------------------------------------------------------------

def json_read_sync(path: str | Path, default: T = None) -> T | Any:
    """Read JSON file with per-file thread lock. Returns default if not found."""
    p = Path(path)
    lock = _get_sync_lock(str(p.resolve()))
    with lock:
        if not p.exists():
            return default
        raw = p.read_text(encoding="utf-8")
        return json.loads(raw)


def json_write_sync(path: str | Path, data: Any, *, indent: int = 2, ensure_ascii: bool = False) -> None:
    """Atomically write JSON with per-file thread lock."""
    p = Path(path)
    lock = _get_sync_lock(str(p.resolve()))
    with lock:
        content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
        _atomic_write_sync(p, content)


def json_update_sync(
    path: str | Path,
    updater: callable,
    *,
    default: Any = None,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> Any:
    """Sync Read-Modify-Write under a single lock."""
    p = Path(path)
    lock = _get_sync_lock(str(p.resolve()))
    with lock:
        if p.exists():
            raw = p.read_text(encoding="utf-8")
            current = json.loads(raw)
        else:
            current = default
        new_data = updater(current)
        content = json.dumps(new_data, indent=indent, ensure_ascii=ensure_ascii)
        _atomic_write_sync(p, content)
        return new_data


# ---------------------------------------------------------------------------
# High-level JsonFileStore class (convenience wrapper)
# ---------------------------------------------------------------------------

class JsonFileStore:
    """Convenience wrapper for a single JSON file with async + sync methods."""

    def __init__(self, path: str | Path, *, default: Any = None):
        self.path = Path(path)
        self.default = default

    def read_sync(self, default: Any = None) -> Any:
        return json_read_sync(self.path, default if default is not None else self.default)

    def write_sync(self, data: Any, *, indent: int = 2, ensure_ascii: bool = False) -> None:
        json_write_sync(self.path, data, indent=indent, ensure_ascii=ensure_ascii)

    def update_sync(self, updater: callable, *, default: Any = None, indent: int = 2, ensure_ascii: bool = False) -> Any:
        return json_update_sync(
            self.path, updater,
            default=default if default is not None else self.default,
            indent=indent, ensure_ascii=ensure_ascii,
        )

    async def read(self, default: Any = None) -> Any:
        return await json_read_async(self.path, default if default is not None else self.default)

    async def write(self, data: Any, *, indent: int = 2, ensure_ascii: bool = False) -> None:
        await json_write_async(self.path, data, indent=indent, ensure_ascii=ensure_ascii)

    async def update(self, updater: callable, *, default: Any = None, indent: int = 2, ensure_ascii: bool = False) -> Any:
        return await json_update_async(
            self.path, updater,
            default=default if default is not None else self.default,
            indent=indent, ensure_ascii=ensure_ascii,
        )
