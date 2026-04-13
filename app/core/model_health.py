"""Model health monitor — periodic LLM connectivity check.

Background task that pings the model endpoint to determine if it is
online, degraded, or offline. Orchestrator uses this to decide whether
to run online paths or switch to offline fallbacks.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.model_router import ModelRouter, ModelClientError

logger = logging.getLogger(__name__)


class ModelHealthStatus(Enum):
    ONLINE = "online"
    DEGRADED = "degraded"       # slow or intermittent
    OFFLINE = "offline"         # completely unreachable
    UNKNOWN = "unknown"         # not yet checked


@dataclass
class ModelHealth:
    status: ModelHealthStatus
    last_check: float = 0.0
    last_response_ms: float = 0.0
    consecutive_failures: int = 0
    error: str | None = None


class ModelHealthMonitor:
    """Background model health checker.

    Periodically sends a minimal probe to the model endpoint and updates
    health status. Orchestrator reads the status to choose online vs
    offline execution paths.
    """

    def __init__(
        self,
        model_router: ModelRouter,
        *,
        check_interval: float = 30.0,
        failure_threshold: int = 3,
        probe_timeout: float = 5.0,
    ) -> None:
        self._model_router = model_router
        self._check_interval = check_interval
        self._failure_threshold = failure_threshold
        self._probe_timeout = probe_timeout
        self._health = ModelHealth(status=ModelHealthStatus.UNKNOWN)
        self._task: asyncio.Task | None = None
        self._running = False

    # -- Lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        """Start background health monitoring."""
        self._running = True
        await self._probe()  # immediate first check
        self._task = asyncio.create_task(self._health_loop())
        logger.info(
            "Model health monitor started, status: %s",
            self._health.status.value,
        )

    async def stop(self) -> None:
        """Stop background monitoring."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Model health monitor stopped")

    async def _health_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._check_interval)
            await self._probe()

    async def _probe(self) -> None:
        """Probe the model endpoint."""
        try:
            start = time.monotonic()
            client = self._model_router.get_client("health_probe")
            await asyncio.wait_for(
                client.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=5,
                ),
                timeout=self._probe_timeout,
            )
            elapsed = (time.monotonic() - start) * 1000

            self._health = ModelHealth(
                status=ModelHealthStatus.ONLINE,
                last_check=time.time(),
                last_response_ms=elapsed,
                consecutive_failures=0,
            )
        except asyncio.TimeoutError:
            self._record_failure("probe timeout")
        except ModelClientError as e:
            self._record_failure(f"model error: {e}")
        except Exception as e:
            self._record_failure(f"unknown: {e}")

    def _record_failure(self, error: str) -> None:
        self._health.consecutive_failures += 1
        self._health.last_check = time.time()
        self._health.error = error

        if self._health.consecutive_failures >= self._failure_threshold:
            self._health.status = ModelHealthStatus.OFFLINE
            logger.warning("Model marked OFFLINE after %d consecutive failures", self._failure_threshold)
        else:
            self._health.status = ModelHealthStatus.DEGRADED

    # -- Public API -----------------------------------------------------------

    @property
    def health(self) -> ModelHealth:
        return self._health

    @property
    def is_online(self) -> bool:
        return self._health.status == ModelHealthStatus.ONLINE

    @property
    def is_offline(self) -> bool:
        return self._health.status == ModelHealthStatus.OFFLINE

    @property
    def is_degraded(self) -> bool:
        return self._health.status == ModelHealthStatus.DEGRADED

    def get_available_paths(self, all_paths: dict[str, Any]) -> list[Any]:
        """Return paths that are available given current model status."""
        available = []
        for path in all_paths.values():
            if path.offline_capable:
                available.append(path)
            elif self.is_online:
                available.append(path)
            # offline + non-capable path → skip
        return available

    async def force_check(self) -> ModelHealth:
        """Force an immediate health check."""
        await self._probe()
        return self._health
