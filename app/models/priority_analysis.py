from __future__ import annotations

from pydantic import BaseModel, Field


class PrioritizedProposal(BaseModel):
    proposal_id: str = Field(..., min_length=1)
    priority_score: int = Field(..., ge=0)
    rank: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1)


class PriorityAnalysisRequest(BaseModel):
    app_instance_id: str = Field(..., min_length=1)


class PriorityAnalysisResult(BaseModel):
    app_instance_id: str
    primary_contradiction: str = Field(..., min_length=1)
    prioritized: list[PrioritizedProposal] = Field(default_factory=list)
    recommended_action: str = Field(..., min_length=1)
