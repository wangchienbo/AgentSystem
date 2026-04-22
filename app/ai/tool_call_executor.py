"""Tool Call Executor — executes tools registered in the UnifiedToolRegistry.

This is the execution engine that:
1. Receives a tool invocation request (tool_id + arguments)
2. Looks up the tool in the registry
3. Validates permissions and visibility
4. Executes the tool handler
5. Returns structured results

Concurrency rule: tool execution runs in PARALLEL (not serialized).
Only model API calls are serialized via CommandQueue.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.models.tool_entry import ToolEntry, ToolType
from app.services.contract_linter import ContractLinter
from app.services.tool_loop_guard import ToolLoopGuard
from app.services.unified_tool_registry import UnifiedToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class ToolCallResult:
    """Result of a tool execution."""
    tool_id: str
    success: bool
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0
    timestamp: str = ""


class ToolCallExecutor:
    """Executes tool calls with permission checking and parallel support."""

    def __init__(
        self,
        registry: UnifiedToolRegistry,
        max_concurrent: int = 10,
        tool_loop_guard: ToolLoopGuard | None = None,
        contract_linter: ContractLinter | None = None,
    ) -> None:
        self._registry = registry
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._call_log: list[dict[str, Any]] = []
        self._tool_loop_guard = tool_loop_guard
        self._contract_linter = contract_linter

    async def call(
        self,
        tool_id: str,
        arguments: dict[str, Any] | None = None,
        caller_id: str | None = None,
        user_role: str = "user",
    ) -> ToolCallResult:
        """Execute a single tool call."""
        entry = self._registry.get(tool_id)
        if not entry:
            return ToolCallResult(
                tool_id=tool_id,
                success=False,
                error=f"Tool not found: {tool_id}",
                timestamp=self._now_iso(),
            )

        if not entry.handler:
            return ToolCallResult(
                tool_id=tool_id,
                success=False,
                error=f"Tool has no handler registered: {tool_id}",
                timestamp=self._now_iso(),
            )

        # Validate arguments with contract linter if configured
        if self._contract_linter and arguments:
            lint_result = self._contract_linter.validate_tool_args(tool_id, arguments)
            if not lint_result.is_valid:
                return ToolCallResult(
                    tool_id=tool_id,
                    success=False,
                    error=f"Contract validation failed: {'; '.join(lint_result.errors)}",
                    timestamp=self._now_iso(),
                )

        # Check tool loop guard if configured
        if self._tool_loop_guard:
            import time
            allowed, reason = self._tool_loop_guard.check_allowed(tool_id, arguments or {}, time.time())
            if not allowed:
                return ToolCallResult(
                    tool_id=tool_id,
                    success=False,
                    error=f"Tool loop guard blocked: {reason}",
                    timestamp=self._now_iso(),
                )

        start = datetime.now(timezone.utc)
        try:
            result = await self._execute(entry, arguments or {})

            # Record successful call
            if self._tool_loop_guard:
                import time
                self._tool_loop_guard.record_call(tool_id, arguments or {}, time.time())

            duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            tool_result = ToolCallResult(
                tool_id=tool_id,
                success=True,
                result=result,
                duration_ms=duration,
                timestamp=self._now_iso(),
            )
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            logger.error("Tool call failed: %s — %s", tool_id, e)
            tool_result = ToolCallResult(
                tool_id=tool_id,
                success=False,
                error=str(e),
                duration_ms=duration,
                timestamp=self._now_iso(),
            )

        self._call_log.append({
            "tool_id": tool_id,
            "caller_id": caller_id,
            "success": tool_result.success,
            "duration_ms": tool_result.duration_ms,
            "timestamp": tool_result.timestamp,
        })
        return tool_result

    async def call_parallel(
        self,
        calls: list[dict[str, Any]],
    ) -> list[ToolCallResult]:
        """Execute multiple tool calls in parallel.

        Each call dict: {"tool_id": ..., "arguments": ..., "caller_id": ...}
        """
        tasks = [
            self._limited_call(
                c["tool_id"],
                c.get("arguments"),
                c.get("caller_id"),
            )
            for c in calls
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _limited_call(
        self,
        tool_id: str,
        arguments: dict[str, Any] | None,
        caller_id: str | None,
    ) -> ToolCallResult:
        """Execute a tool call with concurrency limiting."""
        async with self._semaphore:
            return await self.call(tool_id, arguments, caller_id)

    async def _execute(
        self,
        entry: ToolEntry,
        arguments: dict[str, Any],
    ) -> Any:
        """Execute the tool handler."""
        handler = entry.handler
        if asyncio.iscoroutinefunction(handler):
            return await handler(**arguments)
        elif callable(handler):
            return handler(**arguments)
        else:
            raise TypeError(f"Handler is not callable: {type(handler)}")

    def get_call_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Recent call log for debugging."""
        return self._call_log[-limit:]

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
