from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.system.model_runtime.model_selector import ResolvedModelSelection


@dataclass(frozen=True)
class ModelResolvedCall:
    asset_id: str
    method: str
    params: dict[str, Any]
    resolved_model: ResolvedModelSelection | None
    request_id: str = ""
    target_type: str = ""
    session: dict[str, Any] | None = None
    caller: dict[str, Any] | None = None
    trace_context: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "method": self.method,
            "params": self.params,
            "request_id": self.request_id,
            "target_type": self.target_type,
            "session": self.session,
            "caller": self.caller,
            "trace_context": self.trace_context,
            "metadata": self.metadata,
            "resolved_model": None
            if self.resolved_model is None
            else {
                "model_id": self.resolved_model.model_id,
                "reason": self.resolved_model.reason,
                "provider": self.resolved_model.record.provider,
                "wire_api": self.resolved_model.record.wire_api,
            },
        }
