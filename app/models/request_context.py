"""Request context — identity tracking for every skill invocation.

Carries trace_id, caller_id, user_id, and app_instance_id through the
entire call chain so every log entry and error can be traced back to
the original user and app.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class RequestContext(BaseModel):
    """Identity tracking for a single request through the skill call chain."""

    trace_id: str = Field(..., min_length=1, description="全链路追踪 ID")
    request_id: str = Field(..., min_length=1, description="当前请求 ID")
    user_id: str = Field(..., min_length=1, description="发起请求的用户")
    app_instance_id: str = Field(..., min_length=1, description="所属 App 实例")
    caller_id: str = Field(..., min_length=1, description="直接调用者 (orchestrator / skill.xxx)")
    parent_trace_id: str | None = Field(default=None, description="父级 trace（skill 互调时）")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def new_root(
        cls,
        user_id: str,
        app_instance_id: str,
        caller_id: str = "user",
    ) -> "RequestContext":
        """Create a new root context (user → orchestrator)."""
        trace_id = f"t-{uuid.uuid4().hex[:12]}"
        return cls(
            trace_id=trace_id,
            request_id=str(uuid.uuid4()),
            user_id=user_id,
            app_instance_id=app_instance_id,
            caller_id=caller_id,
        )

    def child(self, caller_id: str) -> "RequestContext":
        """Create a child context for skill-to-skill calls."""
        return RequestContext(
            trace_id=self.trace_id,  # same trace
            request_id=str(uuid.uuid4()),
            user_id=self.user_id,
            app_instance_id=self.app_instance_id,
            caller_id=caller_id,
            parent_trace_id=self.request_id,
        )

    def inject_into_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Inject into request.config for downstream propagation."""
        return {
            **config,
            "__trace_id__": self.trace_id,
            "__request_id__": self.request_id,
            "__user_id__": self.user_id,
            "__app_instance_id__": self.app_instance_id,
            "__caller_id__": self.caller_id,
            "__request_ctx__": self.to_dict(),
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "RequestContext | None":
        """Extract from request.config if present."""
        ctx_dict = config.get("__request_ctx__")
        if not ctx_dict:
            return None
        return cls.model_validate(ctx_dict)
