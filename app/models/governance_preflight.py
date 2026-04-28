from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GovernancePreflightContext(BaseModel):
    recommended_queue_id: str | None = None
    priority_tier: str | None = None
    automation_health: str = "healthy"
    automation_attention_reason: str = ""
    last_tick_outcome: str = "unknown"
    consecutive_failures: int = 0
    retry_pending: bool = False
    priority_lane: str | None = None
    rollout_available: bool = True
    queue_status: str | None = None


class GovernancePreflightDecision(BaseModel):
    recommended_queue_id: str | None = None
    priority_tier: str | None = None
    automation_health: str = "healthy"
    automation_attention_reason: str = ""
    last_tick_outcome: str = "unknown"
    consecutive_failures: int = 0
    queue_status: str | None = None
    priority_lane: str | None = None
    can_apply: bool
    apply_risk: str
    hold_reason: str = ""
    hold_category: str = "none"
    required_review_scope: str
    review_scope: str
    review_reason: str

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
