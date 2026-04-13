"""Async MessageBus — RPC + pub/sub backbone for Skill Workers.

v1 uses in-process asyncio.Queue for transport. The interface is
transport-agnostic so it can later be swapped for HTTP/gRPC without
changing any business logic.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class RpcRequest:
    request_id: str
    target_id: str
    payload: Any
    timeout: float = 30.0


@dataclass
class RpcResponse:
    request_id: str
    result: Any | None = None
    error: str | None = None


class MessageBusError(Exception):
    pass


class WorkerNotFoundError(MessageBusError):
    pass


class RpcTimeoutError(MessageBusError):
    pass


class MessageBus:
    """In-process async message bus for Skill Worker RPC.

    Usage:
        bus = MessageBus()
        bus.register_worker("skill.maoxuan", queue)
        result = await bus.rpc("skill.maoxuan", request)
    """

    def __init__(self) -> None:
        self._worker_queues: dict[str, asyncio.Queue] = {}
        self._pending: dict[str, asyncio.Future] = {}
        self._subscribers: dict[str, list[Callable]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- Registration ---------------------------------------------------------

    def register_worker(self, worker_id: str, queue: asyncio.Queue) -> None:
        """Register a worker's request queue."""
        if worker_id in self._worker_queues:
            logger.warning("Worker already registered: %s, replacing", worker_id)
        self._worker_queues[worker_id] = queue

    def unregister_worker(self, worker_id: str) -> None:
        """Unregister a worker."""
        self._worker_queues.pop(worker_id, None)

    def is_registered(self, worker_id: str) -> bool:
        return worker_id in self._worker_queues

    def list_workers(self) -> list[str]:
        return list(self._worker_queues.keys())

    # -- RPC ------------------------------------------------------------------

    async def rpc(
        self,
        target_id: str,
        payload: Any,
        *,
        timeout: float = 30.0,
    ) -> Any:
        """Send an RPC request and wait for response.

        Args:
            target_id: Worker identifier (skill_id)
            payload: Request object (e.g. SkillExecutionRequest)
            timeout: Seconds to wait for response

        Returns:
            Response result (e.g. SkillExecutionResult)

        Raises:
            WorkerNotFoundError: No worker registered for target_id
            RpcTimeoutError: Response not received within timeout
        """
        if target_id not in self._worker_queues:
            raise WorkerNotFoundError(f"Worker not found: {target_id}")

        request_id = str(uuid.uuid4())
        request = RpcRequest(
            request_id=request_id,
            target_id=target_id,
            payload=payload,
            timeout=timeout,
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        try:
            # Send to worker queue
            await self._worker_queues[target_id].put(request)

            # Wait for response
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise RpcTimeoutError(
                f"RPC timeout: {target_id} did not respond within {timeout}s"
            )
        finally:
            self._pending.pop(request_id, None)

    async def deliver_response(self, request_id: str, result: Any) -> None:
        """Worker calls this to deliver an RPC response."""
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(result)
        else:
            logger.warning("No pending request for response: %s", request_id)

    async def deliver_error(self, request_id: str, error: str) -> None:
        """Worker calls this to deliver an RPC error."""
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_exception(RuntimeError(error))
        else:
            logger.warning("No pending request for error: %s", request_id)

    # -- Pub/Sub --------------------------------------------------------------

    async def publish(self, topic: str, event: Any) -> None:
        """Publish an event to all subscribers of a topic."""
        for handler in self._subscribers.get(topic, []):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Error in subscriber for topic %s", topic)

    async def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe to events on a topic."""
        self._subscribers.setdefault(topic, []).append(handler)

    def unsubscribe(self, topic: str, handler: Callable) -> None:
        """Unsubscribe from a topic."""
        if topic in self._subscribers:
            try:
                self._subscribers[topic].remove(handler)
            except ValueError:
                pass
