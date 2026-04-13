"""SimpleWorker — wraps an existing handler function as a Skill Worker.

Bridges the old `handler(request) -> dict` model to the new Worker
model so existing system skills can run on the MessageBus without
any code changes.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from app.core.skill_worker import SkillWorker
from app.models.skill_meta import SkillMetaInfo

logger = logging.getLogger(__name__)

HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]


class SimpleWorker(SkillWorker):
    """Wraps a callable handler as a Skill Worker on the MessageBus."""

    def __init__(
        self,
        skill_id: str,
        handler: HandlerFn,
        meta: SkillMetaInfo | None = None,
        actions: list[str] | None = None,
    ) -> None:
        self._skill_id = skill_id
        self._handler = handler
        self._meta = meta
        self._actions = actions or ["execute"]
        self._started = False

    @property
    def skill_id(self) -> str:
        return self._skill_id

    @property
    def worker_id(self) -> str:
        return self._skill_id

    @property
    def meta(self) -> SkillMetaInfo:
        if self._meta is None:
            self._meta = SkillMetaInfo(
                skill_id=self._skill_id,
                name=self._skill_id,
                description=f"Wrapped handler: {self._skill_id}",
            )
        return self._meta

    @property
    def available_actions(self) -> list[str]:
        return list(self._actions)

    async def start(self) -> None:
        self._started = True
        logger.info("SimpleWorker started: %s", self._skill_id)

    async def stop(self) -> None:
        self._started = False
        logger.info("SimpleWorker stopped: %s", self._skill_id)

    # -- SkillWorker abstract method implementations --------------------------

    async def init(self, config: dict[str, Any] | None = None) -> None:
        await self.start()

    async def process(self, request: Any) -> Any:
        """Process a request via the handle interface."""
        action = "execute"
        if isinstance(request, dict):
            action = request.get("action", "execute")
        return await self.handle(action, request if isinstance(request, dict) else {})

    async def shutdown(self) -> None:
        await self.stop()

    async def handle(self, action: str, request: dict[str, Any]) -> dict[str, Any]:
        if not self._started:
            return {
                "skill_id": self._skill_id,
                "status": "failed",
                "error": "not started",
            }

        import asyncio
        import inspect

        start_ms = time.monotonic()
        try:
            if inspect.iscoroutinefunction(self._handler):
                result = await self._handler(request)
            else:
                result = self._handler(request)
            elapsed_ms = (time.monotonic() - start_ms) * 1000
            if isinstance(result, dict):
                result.setdefault("skill_id", self._skill_id)
                result.setdefault("status", "completed")
                result["duration_ms"] = elapsed_ms
            return result
        except Exception as e:
            elapsed_ms = (time.monotonic() - start_ms) * 1000
            logger.error("SimpleWorker %s failed: %s", self._skill_id, e)
            return {
                "skill_id": self._skill_id,
                "status": "failed",
                "error": str(e),
                "duration_ms": elapsed_ms,
            }
