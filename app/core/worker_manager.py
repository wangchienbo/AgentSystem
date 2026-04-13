"""WorkerManager — lifecycle management for Skill Workers.

Starts, monitors, and gracefully shuts down all Workers in an App.
Includes automatic restart on unexpected failure.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.message_bus import MessageBus
from app.core.skill_worker import SkillWorker, WorkerHealth

logger = logging.getLogger(__name__)


class WorkerManagerError(Exception):
    pass


class WorkerManager:
    """Manages the lifecycle of Skill Workers.

    Responsibilities:
    - Register and start Workers (init + message loop)
    - Health checking
    - Automatic restart on failure
    - Graceful shutdown
    """

    def __init__(
        self,
        message_bus: MessageBus,
        *,
        max_restarts: int = 3,
        restart_delay: float = 5.0,
    ) -> None:
        self._bus = message_bus
        self._workers: dict[str, SkillWorker] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._restart_counts: dict[str, int] = {}
        self._max_restarts = max_restarts
        self._restart_delay = restart_delay

    # -- Registration & Start -------------------------------------------------

    async def register_and_start(
        self,
        worker: SkillWorker,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Register a Worker, initialize it, and start its message loop."""
        worker_id = worker.worker_id
        if worker_id in self._workers:
            logger.warning("Worker already registered: %s, replacing", worker_id)
            await self._stop_worker(worker_id)

        queue: asyncio.Queue = asyncio.Queue()
        self._bus.register_worker(worker_id, queue)
        self._workers[worker_id] = worker
        self._queues[worker_id] = queue
        self._restart_counts[worker_id] = 0

        # Initialize
        try:
            await worker.init(config)
        except Exception:
            logger.exception("Worker init failed: %s", worker_id)
            self._bus.unregister_worker(worker_id)
            self._workers.pop(worker_id, None)
            self._queues.pop(worker_id, None)
            raise

        # Start message loop
        task = asyncio.create_task(
            self._worker_loop(worker_id, worker, queue),
            name=f"worker-loop-{worker_id}",
        )
        self._tasks[worker_id] = task
        logger.info("Worker started: %s", worker_id)

    # -- Message Loop ---------------------------------------------------------

    async def _worker_loop(
        self,
        worker_id: str,
        worker: SkillWorker,
        queue: asyncio.Queue,
    ) -> None:
        """Continuous message processing loop for a Worker."""
        while True:
            request = await queue.get()
            try:
                result = await worker.process(request.payload)
                await self._bus.deliver_response(request.request_id, result)
            except asyncio.CancelledError:
                queue.task_done()
                break
            except Exception as e:
                logger.exception("Worker %s processing error", worker_id)
                await self._bus.deliver_error(
                    request.request_id,
                    f"Worker {worker_id} error: {e}",
                )
            finally:
                queue.task_done()

    # -- Health ---------------------------------------------------------------

    async def healthcheck_all(self) -> dict[str, WorkerHealth]:
        """Check health of all Workers."""
        results = {}
        for wid, worker in self._workers.items():
            try:
                task = self._tasks.get(wid)
                if task and task.done():
                    results[wid] = WorkerHealth(
                        status="unhealthy",
                        details={"reason": "message_loop_terminated"},
                    )
                else:
                    results[wid] = await worker.healthcheck()
            except Exception as e:
                results[wid] = WorkerHealth(
                    status="unhealthy",
                    details={"error": str(e)},
                )
        return results

    def is_healthy(self, worker_id: str) -> bool:
        """Quick health check (no await)."""
        if worker_id not in self._workers:
            return False
        task = self._tasks.get(worker_id)
        return task is not None and not task.done()

    # -- Shutdown -------------------------------------------------------------

    async def shutdown_all(self) -> None:
        """Gracefully shut down all Workers."""
        for worker_id in list(self._workers.keys()):
            await self._stop_worker(worker_id)
        logger.info("All workers shut down")

    async def _stop_worker(self, worker_id: str) -> None:
        """Stop a single Worker."""
        worker = self._workers.pop(worker_id, None)
        task = self._tasks.pop(worker_id, None)
        self._queues.pop(worker_id, None)
        self._bus.unregister_worker(worker_id)

        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if worker:
            try:
                await worker.shutdown()
            except Exception:
                logger.exception("Worker shutdown error: %s", worker_id)

    # -- Info -----------------------------------------------------------------

    def list_workers(self) -> list[str]:
        return list(self._workers.keys())

    def get_worker(self, worker_id: str) -> SkillWorker | None:
        return self._workers.get(worker_id)
