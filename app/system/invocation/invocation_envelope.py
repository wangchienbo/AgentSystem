from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InvocationSessionRef:
    upstream_session_id: str
    root_session_id: str | None = None
    parent_session_id: str | None = None

    def validate(self) -> None:
        if not self.upstream_session_id or not self.upstream_session_id.strip():
            raise ValueError("upstream_session_id is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "upstream_session_id": self.upstream_session_id,
            "root_session_id": self.root_session_id,
            "parent_session_id": self.parent_session_id,
        }


@dataclass(frozen=True)
class InvocationCallerRef:
    caller_id: str
    caller_type: str

    def validate(self) -> None:
        if not self.caller_id or not self.caller_id.strip():
            raise ValueError("caller_id is required")
        if not self.caller_type or not self.caller_type.strip():
            raise ValueError("caller_type is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller_id": self.caller_id,
            "caller_type": self.caller_type,
        }


@dataclass(frozen=True)
class InvocationRequestEnvelope:
    request_id: str
    target_id: str
    target_type: str
    method: str
    args: dict[str, Any] = field(default_factory=dict)
    session: InvocationSessionRef | None = None
    caller: InvocationCallerRef | None = None
    trace_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.request_id or not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.target_id or not self.target_id.strip():
            raise ValueError("target_id is required")
        if not self.target_type or not self.target_type.strip():
            raise ValueError("target_type is required")
        if not self.method or not self.method.strip():
            raise ValueError("method is required")
        if not isinstance(self.args, dict):
            raise ValueError("args must be an object")
        if self.session is not None:
            self.session.validate()
        if self.caller is not None:
            self.caller.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "method": self.method,
            "args": self.args,
            "session": None if self.session is None else self.session.to_dict(),
            "caller": None if self.caller is None else self.caller.to_dict(),
            "trace_context": self.trace_context,
            "metadata": self.metadata,
        }

    @classmethod
    def from_legacy(
        cls,
        *,
        asset_id: str,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: str = "legacy-request",
        target_type: str = "system_asset",
    ) -> "InvocationRequestEnvelope":
        return cls(
            request_id=request_id,
            target_id=asset_id,
            target_type=target_type,
            method=method,
            args=params or {},
        )


@dataclass(frozen=True)
class InvocationResponseEnvelope:
    ok: bool
    request_id: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_type: str | None = None
    resolved_local_session_id: str | None = None
    trace_context: dict[str, Any] = field(default_factory=dict)
    state_updates: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.request_id or not self.request_id.strip():
            raise ValueError("request_id is required")
        if not isinstance(self.ok, bool):
            raise ValueError("ok must be boolean")
        if not isinstance(self.data, dict):
            raise ValueError("data must be an object")
        if self.error_type is not None and not self.error_type.strip():
            raise ValueError("error_type must not be empty when provided")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "request_id": self.request_id,
            "data": self.data,
            "error": self.error,
            "error_type": self.error_type,
            "resolved_local_session_id": self.resolved_local_session_id,
            "trace_context": self.trace_context,
            "state_updates": self.state_updates,
            "metadata": self.metadata,
        }
