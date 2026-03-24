from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


SkillRiskDecisionStatus = Literal["approved_override", "revoked"]
SkillRiskDecisionScope = Literal["generated_app_assembly"]
SkillRiskGovernanceEventType = Literal["policy_blocked", "override_approved", "override_revoked"]


class SkillRiskDecision(BaseModel):
    skill_id: str = Field(..., min_length=1)
    decision: SkillRiskDecisionStatus = "approved_override"
    scope: SkillRiskDecisionScope = "generated_app_assembly"
    reviewer: str = Field(..., min_length=1)
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    def is_active(self, now: datetime | None = None) -> bool:
        if self.decision != "approved_override":
            return False
        now = now or datetime.now(UTC)
        if self.expires_at is None:
            return True
        return self.expires_at > now


class SkillRiskGovernanceEvent(BaseModel):
    skill_id: str = Field(..., min_length=1)
    event_type: SkillRiskGovernanceEventType
    scope: SkillRiskDecisionScope = "generated_app_assembly"
    actor: str = Field(default="system", min_length=1)
    reason: str = Field(default="")
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
