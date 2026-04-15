"""Skill RPC Response — structured response model for skill invocations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Unified RPC error codes
RPC_SUCCESS = 0
RPC_BAD_REQUEST = 400
RPC_UNAUTHORIZED = 401
RPC_FORBIDDEN = 403
RPC_NOT_FOUND = 404
RPC_INTERNAL_ERROR = 500
RPC_UNAVAILABLE = 503

ERROR_MESSAGES: dict[int, str] = {
    RPC_SUCCESS: "Success",
    RPC_BAD_REQUEST: "Bad request",
    RPC_UNAUTHORIZED: "Unauthorized",
    RPC_FORBIDDEN: "Forbidden",
    RPC_NOT_FOUND: "Not found",
    RPC_INTERNAL_ERROR: "Internal error",
    RPC_UNAVAILABLE: "Service unavailable",
}


@dataclass
class SkillRpcResponse:
    """Standard RPC response for any skill invocation.

    Attributes:
        code: Error code (0 = success)
        message: Human-readable status message
        data: Response payload (skill-specific)
        trace_id: Same trace_id from request for chain tracing
        skill_id: Which skill produced this response
        action: Which action was executed
        duration_ms: Execution duration in milliseconds
    """
    code: int = RPC_SUCCESS
    message: str = "Success"
    data: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    skill_id: str = ""
    action: str = ""
    duration_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.code == RPC_SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "data": self.data,
            "trace_id": self.trace_id,
            "skill_id": self.skill_id,
            "action": self.action,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillRpcResponse":
        return cls(
            code=data.get("code", RPC_SUCCESS),
            message=data.get("message", "Success"),
            data=data.get("data", {}),
            trace_id=data.get("trace_id", ""),
            skill_id=data.get("skill_id", ""),
            action=data.get("action", ""),
            duration_ms=data.get("duration_ms", 0.0),
        )

    @classmethod
    def error(cls, code: int, message: str | None = None, trace_id: str = "",
              skill_id: str = "", action: str = "") -> "SkillRpcResponse":
        return cls(
            code=code,
            message=message or ERROR_MESSAGES.get(code, "Unknown error"),
            trace_id=trace_id,
            skill_id=skill_id,
            action=action,
        )

    @classmethod
    def success(cls, data: dict[str, Any] | None = None, trace_id: str = "",
                skill_id: str = "", action: str = "") -> "SkillRpcResponse":
        return cls(
            code=RPC_SUCCESS,
            message="Success",
            data=data or {},
            trace_id=trace_id,
            skill_id=skill_id,
            action=action,
        )
