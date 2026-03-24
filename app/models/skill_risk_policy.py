from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from app.models.operator_dashboards import OperatorDashboardCore
from app.models.operator_contracts import OperatorPageMeta
from pydantic import BaseModel, Field


SkillRiskDecisionStatus = Literal["approved_override", "revoked"]
SkillRiskDecisionScope = Literal["generated_app_assembly", "blueprint_materialization"]
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


class SkillRiskEventPage(BaseModel):
    items: list[SkillRiskGovernanceEvent] = Field(default_factory=list)
    meta: OperatorPageMeta = Field(default_factory=OperatorPageMeta)


class SkillRiskStatsSummary(BaseModel):
    total_decisions: int = 0
    active_overrides: int = 0
    revoked_overrides: int = 0
    total_events: int = 0
    blocked_events: int = 0
    approved_events: int = 0
    revoked_events: int = 0
    latest_decision_at: datetime | None = None
    latest_event_at: datetime | None = None


class SkillRiskDashboard(OperatorDashboardCore[dict[str, Any], SkillRiskStatsSummary]):
    recent_events: SkillRiskEventPage
