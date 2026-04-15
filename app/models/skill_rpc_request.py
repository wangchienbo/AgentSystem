"""Skill RPC Request — structured request model for skill invocations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillRpcRequest:
    """Standard RPC request for any skill invocation.

    This model is the unified contract for calling any skill, regardless
    of whether it runs in the same process or a remote App process.

    Attributes:
        skill_id: Target skill identifier (e.g. "skill.maoxuan")
        action: Action/method within the skill (e.g. "analyze", "create")
        user_request: Natural language user request
        context: Structured context dict (session, user info, etc.)
        trace_id: Global unique trace ID for the entire request chain
        caller_id: Who initiated this request (app_id, gateway, etc.)
        user_id: End user identifier
        timestamp: Request timestamp (ISO format)
        timeout: Timeout in seconds
    """
    skill_id: str
    action: str
    user_request: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    caller_id: str = ""
    user_id: str | None = None
    timestamp: str = ""
    timeout: int = 300

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "action": self.action,
            "user_request": self.user_request,
            "context": self.context,
            "trace_id": self.trace_id,
            "caller_id": self.caller_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillRpcRequest":
        return cls(
            skill_id=data.get("skill_id", ""),
            action=data.get("action", ""),
            user_request=data.get("user_request", ""),
            context=data.get("context", {}),
            trace_id=data.get("trace_id", ""),
            caller_id=data.get("caller_id", ""),
            user_id=data.get("user_id"),
            timestamp=data.get("timestamp", ""),
            timeout=data.get("timeout", 300),
        )
