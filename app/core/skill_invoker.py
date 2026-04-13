"""Skill-to-Skill Invocation Engine (Phase F.10).

Provides a unified interface for skills to call other skills with:
- Call chain tracking (full ancestry)
- Cycle detection (prevent A→B→A deadlocks)
- Max depth limit (prevent infinite recursion)
- Per-call timeout
- Result aggregation
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.models.skill_runtime import SkillExecutionRequest, SkillExecutionResult


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SkillInvocationError(Exception):
    """Base exception for skill invocation failures."""


class SkillCycleError(SkillInvocationError):
    """Circular skill call detected."""


class SkillDepthLimitError(SkillInvocationError):
    """Max call depth exceeded."""


class SkillTimeoutError(SkillInvocationError):
    """Skill call exceeded timeout."""


class SkillNotFoundError(SkillInvocationError):
    """Target skill does not exist or is disabled."""


# ---------------------------------------------------------------------------
# Call chain tracking
# ---------------------------------------------------------------------------

@dataclass
class CallFrame:
    """A single frame in the skill call chain."""
    skill_id: str
    inputs: dict[str, Any]
    started_at: float  # monotonic
    finished_at: float | None = None
    result: SkillExecutionResult | None = None
    error: str | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at) * 1000


@dataclass
class InvocationContext:
    """Carries the full call chain + execution guard through skill invocations."""
    root_skill_id: str
    root_app_instance_id: str
    root_workflow_id: str
    chain: list[CallFrame] = field(default_factory=list)
    max_depth: int = 10
    default_timeout_seconds: float = 30.0

    @property
    def depth(self) -> int:
        return len(self.chain)

    def push(self, skill_id: str, inputs: dict[str, Any]) -> CallFrame:
        frame = CallFrame(skill_id=skill_id, inputs=inputs, started_at=time.monotonic())
        self.chain.append(frame)
        return frame

    def pop(self, frame: CallFrame, result: SkillExecutionResult | None = None, error: str | None = None) -> None:
        frame.finished_at = time.monotonic()
        frame.result = result
        frame.error = error
        # Keep frame in chain for audit trail

    def check_cycle(self, skill_id: str) -> None:
        """Raise SkillCycleError if skill_id is already in the call chain."""
        for frame in self.chain:
            if frame.skill_id == skill_id:
                chain_str = " → ".join(f.skill_id for f in self.chain) + f" → {skill_id}"
                raise SkillCycleError(
                    f"Cycle detected: {chain_str}. "
                    f"Skill '{skill_id}' is already in the call chain."
                )

    def check_depth(self) -> None:
        """Raise SkillDepthLimitError if max depth exceeded."""
        if self.depth >= self.max_depth:
            chain_str = " → ".join(f.skill_id for f in self.chain[-3:])
            raise SkillDepthLimitError(
                f"Max call depth ({self.max_depth}) exceeded. "
                f"Current chain tail: …{chain_str}"
            )

    def check_timeout(self, timeout: float) -> None:
        """Raise SkillTimeoutError if current frame exceeded timeout."""
        if not self.chain:
            return
        current = self.chain[-1]
        elapsed = time.monotonic() - current.started_at
        if elapsed > timeout:
            raise SkillTimeoutError(
                f"Skill '{current.skill_id}' exceeded timeout ({timeout:.1f}s, "
                f"elapsed {elapsed:.1f}s)"
            )

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable call chain snapshot."""
        return {
            "root": self.root_skill_id,
            "depth": self.depth,
            "chain": [
                {
                    "skill_id": f.skill_id,
                    "duration_ms": f.duration_ms,
                    "status": "running" if f.finished_at is None else (
                        "ok" if f.error is None else "failed"
                    ),
                }
                for f in self.chain
            ],
        }


# ---------------------------------------------------------------------------
# SkillInvoker — the unified calling interface
# ---------------------------------------------------------------------------

class SkillInvoker:
    """Execute other skills from within a skill, with guard rails.

    Usage inside a skill handler:
        def my_handler(request: SkillExecutionRequest) -> SkillExecutionResult:
            invoker: SkillInvoker = request.config.get("__invoker__")
            result = invoker.invoke(
                skill_id="text-normalize",
                inputs={"text": request.inputs["raw_text"]},
            )
            return SkillExecutionResult(
                skill_id=request.skill_id,
                output={"normalized": result.output.get("text", "")},
            )
    """

    def __init__(
        self,
        execute_fn,  # Callable[[SkillExecutionRequest], SkillExecutionResult]
        context: InvocationContext,
    ):
        self._execute = execute_fn
        self._ctx = context

    def invoke(
        self,
        skill_id: str,
        inputs: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> SkillExecutionResult:
        """Synchronously invoke another skill.

        Args:
            skill_id: Target skill identifier
            inputs: Input payload for the target skill
            timeout: Override timeout in seconds (uses context default if None)

        Returns:
            SkillExecutionResult from the target skill

        Raises:
            SkillNotFoundError: Skill doesn't exist or is disabled
            SkillCycleError: Circular call detected
            SkillDepthLimitError: Max call depth exceeded
            SkillTimeoutError: Execution exceeded timeout
        """
        inputs = inputs or {}
        effective_timeout = timeout or self._ctx.default_timeout_seconds

        # Guard 1: Cycle detection
        self._ctx.check_cycle(skill_id)

        # Guard 2: Depth limit
        self._ctx.check_depth()

        # Push a new frame
        frame = self._ctx.push(skill_id, inputs)

        try:
            request = SkillExecutionRequest(
                skill_id=skill_id,
                app_instance_id=self._ctx.root_app_instance_id,
                workflow_id=self._ctx.root_workflow_id,
                step_id=f"invoke.{self._ctx.depth}",
                inputs=inputs,
                config={"__invoker__": self, "__invocation_ctx__": self._ctx},
            )

            result = self._execute(request)

            # Guard 3: Check timeout after execution
            self._ctx.check_timeout(effective_timeout)

            self._ctx.pop(frame, result=result)
            return result

        except (SkillCycleError, SkillDepthLimitError, SkillTimeoutError):
            self._ctx.pop(frame, error="invocation_guard")
            raise
        except Exception as e:
            self._ctx.pop(frame, error=str(e))
            raise SkillInvocationError(
                f"Failed to invoke skill '{skill_id}': {e}"
            ) from e

    @property
    def context(self) -> InvocationContext:
        return self._ctx


# ---------------------------------------------------------------------------
# Convenience: create InvocationContext from a root request
# ---------------------------------------------------------------------------

def create_invocation_context(
    request: SkillExecutionRequest,
    *,
    max_depth: int = 10,
    default_timeout: float = 30.0,
) -> InvocationContext:
    """Create a fresh InvocationContext for a top-level skill execution."""
    return InvocationContext(
        root_skill_id=request.skill_id,
        root_app_instance_id=request.app_instance_id,
        root_workflow_id=request.workflow_id,
        max_depth=max_depth,
        default_timeout_seconds=default_timeout,
    )


def get_invoker_from_request(request: SkillExecutionRequest) -> SkillInvoker | None:
    """Extract SkillInvoker from a request's config (for use inside skill handlers)."""
    return request.config.get("__invoker__")


def get_context_from_request(request: SkillExecutionRequest) -> InvocationContext | None:
    """Extract InvocationContext from a request's config."""
    return request.config.get("__invocation_ctx__")
