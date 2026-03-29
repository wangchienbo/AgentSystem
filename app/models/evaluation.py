from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

EvaluationTargetType = Literal["app", "skill", "agent", "policy"]


class CandidateEvaluationRecord(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    target_type: EvaluationTargetType
    target_id: str = Field(..., min_length=1)
    baseline_version: str = Field(..., min_length=1)
    candidate_version: str = Field(..., min_length=1)
    success_delta: float = 0.0
    token_delta: float = 0.0
    latency_delta: float = 0.0
    feedback_delta: float = 0.0
    stability_delta: float = 0.0
    accepted: bool = False
    rejection_reason: str = ""
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvaluationGatePolicy(BaseModel):
    max_token_growth: float = 0.15
    max_latency_growth: float = 0.20
    min_success_delta: float = -0.02
    min_stability_delta: float = -0.02
