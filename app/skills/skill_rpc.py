"""Skill RPC Service — unified RPC interface for all skill invocations.

This service provides the single entry point for calling any skill in the
AgentSystem, whether the skill runs in the same process or a remote App
process. All callers (Gateway, App Orchestrator, other Skills) use this
service with a SkillRpcRequest and receive a SkillRpcResponse.

Design principles:
- skill_id + action routing — no special cases for "internal" calls
- Full identity tracing (trace_id, caller_id, user_id)
- Unified error codes (0, 400, 401, 403, 404, 500, 503)
- Duration tracking for every invocation
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from app.core.message_bus import MessageBus
from app.core.skill_worker import SkillWorker
from app.core.worker_manager import WorkerManager
from app.models.skill_rpc_request import SkillRpcRequest
from app.models.skill_rpc_response import (
    SkillRpcResponse,
    RPC_INTERNAL_ERROR,
    RPC_NOT_FOUND,
    RPC_UNAVAILABLE,
)


class SkillRpcService:
    """Unified RPC gateway for all skill invocations.

    In single-process mode (AGENTSYSTEM_MODE=single):
    - Resolves skill_id → local SkillWorker via WorkerManager
    - Calls worker.process() directly

    In distributed mode (AGENTSYSTEM_MODE=distributed):
    - Sends RPC via MessageBus to the App process owning the skill
    - Awaits response with timeout

    All callers use the same interface — no "internal call" shortcuts.
    """

    def __init__(
        self,
        worker_manager: WorkerManager | None = None,
        message_bus: MessageBus | None = None,
        distributed: bool = False,
    ) -> None:
        self._worker_manager = worker_manager
        self._message_bus = message_bus
        self._distributed = distributed

    async def call(self, request: SkillRpcRequest) -> SkillRpcResponse:
        """Execute a skill RPC call.

        In single-process mode: resolves to local worker and calls process().
        In distributed mode: sends via MessageBus RPC.

        Args:
            request: Structured RPC request

        Returns:
            Structured RPC response
        """
        start = time.monotonic()

        try:
            if self._distributed and self._message_bus:
                result = await self._call_remote(request)
            else:
                result = await self._call_local(request)
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SkillRpcResponse(
                code=RPC_INTERNAL_ERROR,
                message=f"Skill RPC failed: {e}",
                trace_id=request.trace_id,
                skill_id=request.skill_id,
                action=request.action,
                duration_ms=elapsed,
            )

        elapsed = (time.monotonic() - start) * 1000
        result.duration_ms = elapsed
        if not result.trace_id:
            result.trace_id = request.trace_id
        if not result.skill_id:
            result.skill_id = request.skill_id
        if not result.action:
            result.action = request.action
        return result

    async def _call_local(self, request: SkillRpcRequest) -> SkillRpcResponse:
        """Call a skill worker in the local process."""
        if not self._worker_manager:
            return SkillRpcResponse(
                code=RPC_UNAVAILABLE,
                message="WorkerManager not available",
                trace_id=request.trace_id,
                skill_id=request.skill_id,
                action=request.action,
            )

        worker = self._worker_manager.get_worker(request.skill_id)
        if not worker:
            return SkillRpcResponse(
                code=RPC_NOT_FOUND,
                message=f"Skill not found: {request.skill_id}",
                trace_id=request.trace_id,
                skill_id=request.skill_id,
                action=request.action,
            )

        try:
            result = await worker.process(request)
            if isinstance(result, SkillRpcResponse):
                return result
            # Wrap raw result in response
            return SkillRpcResponse.success(
                data={"result": result} if result is not None else {},
                trace_id=request.trace_id,
                skill_id=request.skill_id,
                action=request.action,
            )
        except Exception as e:
            return SkillRpcResponse(
                code=RPC_INTERNAL_ERROR,
                message=f"Skill execution error: {e}",
                trace_id=request.trace_id,
                skill_id=request.skill_id,
                action=request.action,
            )

    async def _call_remote(self, request: SkillRpcRequest) -> SkillRpcResponse:
        """Call a skill worker in a remote App process via MessageBus."""
        if not self._message_bus:
            return SkillRpcResponse(
                code=RPC_UNAVAILABLE,
                message="MessageBus not available for remote call",
                trace_id=request.trace_id,
                skill_id=request.skill_id,
                action=request.action,
            )

        # Use MessageBus RPC with timeout
        response = await self._message_bus.rpc(
            target=request.skill_id,
            method="process",
            payload=request.to_dict(),
            timeout=request.timeout,
        )

        if isinstance(response, dict):
            return SkillRpcResponse.from_dict(response)
        return SkillRpcResponse.success(
            data={"result": response},
            trace_id=request.trace_id,
            skill_id=request.skill_id,
            action=request.action,
        )

    def register_worker(self, skill_id: str, worker: SkillWorker) -> None:
        """Register a skill worker for local calls.

        In single-process mode, this is how skills become callable.
        """
        if self._worker_manager:
            self._worker_manager.register_worker(skill_id, worker)
