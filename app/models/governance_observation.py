from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ObservationEvidenceKind = Literal[
    "input",
    "routing",
    "tool_selection",
    "execution",
    "output",
    "user_feedback",
]

ObservationFailureStage = Literal[
    "requirement_understanding",
    "routing",
    "evidence",
    "execution",
    "answer_shaping",
]

ObservationDomain = Literal[
    "automation_control_plane",
    "regression_quality",
]

ObservationScope = Literal[
    "fixed_regression",
    "live_chat",
    "replay_regression",
    "nightly_governance",
    "manual_governance",
]


class EvidenceEnvelope(BaseModel):
    kind: ObservationEvidenceKind
    summary: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    grade: Literal["none", "weak", "excerpt", "direct", "derived"] = "derived"
    refs: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("refs")
    @classmethod
    def _normalize_refs(cls, refs: list[str]) -> list[str]:
        return [item.strip() for item in refs if item and item.strip()]


class ObservationRecord(BaseModel):
    observation_id: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    session_id: str | None = None
    trace_id: str | None = None
    source: str = Field(..., min_length=1)
    scope: ObservationScope = "fixed_regression"
    domain: ObservationDomain = "regression_quality"
    subdomain: str = Field(default="general", min_length=1)
    signal: str = Field(default="unknown", min_length=1)
    success: bool
    failure_stage: ObservationFailureStage | None = None
    evidence: list[EvidenceEnvelope] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, tags: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in tags:
            cleaned = tag.strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @model_validator(mode="after")
    def _validate_failure_stage(self) -> "ObservationRecord":
        if self.success and self.failure_stage is not None:
            raise ValueError("successful observations must not set failure_stage")
        if not self.success and self.failure_stage is None:
            raise ValueError("failed observations must set failure_stage")
        return self


class GovernanceEvidenceDigest(BaseModel):
    total_observations: int = 0
    dominant_failure_stage: str | None = None
    dominant_evidence_kind: str | None = None
    failure_stage_counts: dict[str, int] = Field(default_factory=dict)
    evidence_kind_counts: dict[str, int] = Field(default_factory=dict)
    topic_failure_stage_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    observation_samples: list[ObservationRecord] = Field(default_factory=list)


class ReplayRegressionSample(BaseModel):
    sample_id: str = Field(..., min_length=1)
    source_session_id: str = Field(..., min_length=1)
    prompt_seed_id: str | None = None
    topic: str = Field(..., min_length=1)
    user_input_excerpt: str = Field(..., min_length=1, max_length=2000)
    expected_outcome_summary: str = Field(..., min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("evidence_refs")
    @classmethod
    def _normalize_evidence_refs(cls, refs: list[str]) -> list[str]:
        return [item.strip() for item in refs if item and item.strip()]
