"""Protocol adapters — unify different skill invocation protocols.

All skill types (callable, script, executable, worker, http) are
wrapped behind a single async invoke() interface returning
SkillExecutionResult.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult

logger = logging.getLogger(__name__)


class ProtocolAdapter(ABC):
    """Base protocol adapter for skill invocation."""

    adapter_type: str

    @abstractmethod
    async def invoke(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """Unified invocation interface."""


class CallableAdapter(ProtocolAdapter):
    """Direct Python function call (legacy compatibility)."""

    adapter_type = "callable"

    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def invoke(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        # Handlers are synchronous — run in thread pool if needed
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._handler, request)
        return result


class ScriptAdapter(ProtocolAdapter):
    """Script execution via subprocess with JSON I/O."""

    adapter_type = "script"

    def __init__(self, command: list[str], entry: str, timeout: float = 30.0) -> None:
        self._command = command
        self._entry = entry
        self._timeout = timeout

    async def invoke(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        payload = json.dumps({
            "skill_id": request.skill_id,
            "action": request.action,
            "inputs": request.inputs,
            "config": request.config,
        })

        cmd = [*self._command, self._entry] if self._entry else self._command
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=payload.encode()),
                timeout=self._timeout,
            )

            if proc.returncode != 0:
                return SkillExecutionResult(
                    skill_id=request.skill_id,
                    status="failed",
                    output={},
                    error=stderr.decode(errors="replace"),
                )

            data = json.loads(stdout.decode())
            return SkillExecutionResult(
                skill_id=request.skill_id,
                status=data.get("status", "completed"),
                output=data.get("output", {}),
                error=data.get("error"),
            )
        except asyncio.TimeoutError:
            return SkillExecutionResult(
                skill_id=request.skill_id,
                status="failed",
                output={},
                error=f"Script timed out after {self._timeout}s",
            )


class WorkerAdapter(ProtocolAdapter):
    """MessageBus RPC invocation."""

    adapter_type = "worker"

    def __init__(self, bus: Any, timeout: float = 30.0) -> None:
        self._bus = bus
        self._timeout = timeout

    async def invoke(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        result = await self._bus.rpc(request.skill_id, request, timeout=self._timeout)
        if isinstance(result, SkillExecutionResult):
            return result
        if isinstance(result, dict):
            return SkillExecutionResult(
                skill_id=request.skill_id,
                status=result.get("status", "completed"),
                output=result.get("output", {}),
                error=result.get("error"),
            )
        return SkillExecutionResult(
            skill_id=request.skill_id,
            status="completed",
            output={"raw": result},
        )


class HttpAdapter(ProtocolAdapter):
    """Remote HTTP skill invocation."""

    adapter_type = "http"

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def invoke(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        import aiohttp
        url = f"{self._base_url}/skills/{request.skill_id}/invoke"
        body = {
            "action": request.action,
            "inputs": request.inputs,
            "config": request.config,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    data = await resp.json()
                    return SkillExecutionResult(
                        skill_id=request.skill_id,
                        status=data.get("status", "completed"),
                        output=data.get("output", {}),
                        error=data.get("error"),
                    )
        except Exception as e:
            return SkillExecutionResult(
                skill_id=request.skill_id,
                status="failed",
                output={},
                error=f"HTTP request failed: {e}",
            )
