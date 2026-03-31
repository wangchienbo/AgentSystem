from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskGovernanceOperation = Literal["events", "stats", "dashboard", "approve_override", "revoke_override"]


class RiskGovernanceSkillRequest(BaseModel):
    operation: RiskGovernanceOperation
    skill_id: str = ""
    reviewer: str = "system"
    reason: str = ""
    limit: int | None = Field(default=None, ge=1)
