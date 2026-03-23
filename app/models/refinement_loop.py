from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


HypothesisStatus = Literal["proposed", "approved", "rejected", "superseded"]
ExperimentStatus = Literal["planned", "running", "completed", "aborted"]
VerificationOutcome = Literal["passed", "failed", "inconclusive"]
RolloutDecisionStatus = Literal["promote", "hold", "reject"]
RolloutQueueStatus = Literal["queued", "approved", "applied", "rejected", "rolled_back"]


class RefinementHypothesis(BaseModel):
    hypothesis_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    proposal_id: str = Field(..., min_length=1)
    experience_id: str = Field(..., min_length=1)
    contradiction: str = Field(..., min_length=1)
    hypothesis: str = Field(..., min_length=1)
    expected_change: str = Field(..., min_length=1)
    evidence: list[str] = Field(default_factory=list)
    status: HypothesisStatus = "proposed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RefinementExperiment(BaseModel):
    experiment_id: str = Field(..., min_length=1)
    hypothesis_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    workflow_id: str = Field(default="")
    validation_plan: list[str] = Field(default_factory=list)
    validation_mode: str = Field(default="checklist")
    status: ExperimentStatus = "planned"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VerificationResult(BaseModel):
    verification_id: str = Field(..., min_length=1)
    hypothesis_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    outcome: VerificationOutcome
    summary: str = Field(..., min_length=1)
    passed_checks: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    execution_reference: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RolloutDecision(BaseModel):
    decision_id: str = Field(..., min_length=1)
    hypothesis_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    status: RolloutDecisionStatus
    reason: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RolloutQueueItem(BaseModel):
    queue_id: str = Field(..., min_length=1)
    hypothesis_id: str = Field(..., min_length=1)
    proposal_id: str = Field(..., min_length=1)
    app_instance_id: str = Field(..., min_length=1)
    status: RolloutQueueStatus = "queued"
    note: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RefinementOverview(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    hypothesis_count: int = 0
    unresolved_hypothesis_count: int = 0
    verification_count: int = 0
    passed_verification_count: int = 0
    failed_verification_count: int = 0
    decision_count: int = 0
    promote_count: int = 0
    hold_count: int = 0
    queue_count: int = 0
    queued_count: int = 0
    applied_count: int = 0
    latest_hypothesis: RefinementHypothesis | None = None
    latest_verification: VerificationResult | None = None
    latest_decision: RolloutDecision | None = None
    latest_queue_item: RolloutQueueItem | None = None


class RefinementLoopRequest(BaseModel):
    app_instance_id: str = Field(..., min_length=1)
    experience_id: str = Field(..., min_length=1)


class RefinementLoopResult(BaseModel):
    app_instance_id: str
    experience_id: str
    primary_contradiction: str = Field(..., min_length=1)
    hypothesis: RefinementHypothesis
    experiment: RefinementExperiment
    verification: VerificationResult
    rollout: RolloutDecision
    queue_item: RolloutQueueItem | None = None
