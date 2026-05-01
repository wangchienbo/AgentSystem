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

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "method": self.method,
            "params": self.params,
            "resolved_model": None
            if self.resolved_model is None
            else {
                "model_id": self.resolved_model.model_id,
                "reason": self.resolved_model.reason,
                "provider": self.resolved_model.record.provider,
                "wire_api": self.resolved_model.record.wire_api,
            },
        }
