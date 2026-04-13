"""Skill Worker — persistent, RPC-callable skill component.

Every skill in the AgentSystem runs as a persistent Worker inside an App.
Workers are started at App boot, communicate via MessageBus RPC, and
manage their own internal lifecycle (including optional LLM calls).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkerHealth:
    """Health status of a Skill Worker."""
    status: str  # "healthy" | "degraded" | "unhealthy"
    details: dict[str, Any] = field(default_factory=dict)


class SkillWorker(ABC):
    """Base class for all Skill Workers.

    Subclasses must implement:
    - init(): called at App startup to load models/resources
    - process(): called for each RPC invocation
    - shutdown(): called at App teardown to cleanup

    A Worker supports multiple actions via request.action routing.
    Whether it calls LLM internally is entirely up to the Worker.
    """

    worker_id: str  # matches skill_id, e.g. "skill.maoxuan"

    @abstractmethod
    async def init(self, config: dict[str, Any] | None = None) -> None:
        """Called once at App startup. Load models, open connections, etc."""

    @abstractmethod
    async def process(self, request: Any) -> Any:
        """Handle one RPC invocation. Return structured result."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Called once at App teardown. Release resources."""

    async def healthcheck(self) -> WorkerHealth:
        """Optional health check. Override for detailed status."""
        return WorkerHealth(status="healthy")
