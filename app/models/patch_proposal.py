from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PatchTarget = Literal["workflow", "runtime_policy", "skill"]
RiskLevel = Literal["low", "medium", "high"]


class PatchProposal(BaseModel):
    proposal_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    target_type: PatchTarget
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    evidence: list[str] = Field(default_factory=list)
    expected_benefit: str = Field(..., min_length=1)
    risk_level: RiskLevel = "low"
    auto_apply_allowed: bool = False
    validation_checklist: list[str] = Field(default_factory=list)
    rollback_target: str = Field(..., min_length=1)
    patch: dict = Field(default_factory=dict)


class SelfRefinementRequest(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    experience_id: str = Field(..., min_length=1)


class SelfRefinementResult(BaseModel):
    app_instance_id: str
    experience_id: str
    proposals: list[PatchProposal] = Field(default_factory=list)
