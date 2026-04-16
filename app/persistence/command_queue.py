"""Command Queue — priority queue for model API calls.

Key rule: user intent is ALWAYS P0 and jumps to the front.
This queue only manages model API calls (which are serialized).
User requests and tool execution run in parallel outside this queue.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Awaitable, Callable


class Priority(IntEnum):
    P0_USER_INTENT = 0      # User new message — always jumps front
    P1_ACTIVE_TASK = 1      # Active task continuation
    P2_BACKGROUND = 2       # Background / scheduled work


@dataclass(order=True)
class QueuedCommand:
    priority: Priority
    sequence: int = field(compare=True)
    command_id: str = field(compare=False)
    callable: Awaitable = field(compare=False)
    metadata: dict[str, Any] = field(compare=False, default_factory=dict)


class CommandQueue:
    """Priority queue for serialized model API calls.

    User new messages (P0) always jump to the front,
    even ahead of currently-waiting model requests.
    """

    def __init__(self) -> None:
        self._queue: list[QueuedCommand] = []
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._event = asyncio.Event()

    async def enqueue(
        self,
        command_id: str,
        callable: Awaitable,
        priority: Priority = Priority.P1_ACTIVE_TASK,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a command to the queue.

        P0 commands are inserted at the front.
        Others are appended in sequence order.
        """
        async with self._lock:
            self._sequence += 1
            item = QueuedCommand(
                priority=priority,
                sequence=self._sequence,
                command_id=command_id,
                callable=callable,
                metadata=metadata or {},
            )
            if priority == Priority.P0_USER_INTENT:
                # P0 jumps to front, maintaining FIFO among P0s
                insert_pos = 0
                for i, existing in enumerate(self._queue):
                    if existing.priority == Priority.P0_USER_INTENT:
                        insert_pos = i + 1
                    else:
                        break
                self._queue.insert(insert_pos, item)
            else:
                self._queue.append(item)
            self._event.set()

    async def dequeue(self) -> QueuedCommand | None:
        """Get the next command from the queue."""
        async with self._lock:
            if not self._queue:
                return None
            return self._queue.pop(0)

    async def wait_for_item(self, timeout: float = 60.0) -> QueuedCommand | None:
        """Wait until there is an item in the queue."""
        self._event.clear()
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return await self.dequeue()

    def size(self) -> int:
        """Current queue length."""
        return len(self._queue)

    def clear(self) -> None:
        """Clear all queued items."""
        self._queue.clear()
        self._event.clear()
