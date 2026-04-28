from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

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


class EvidenceEnvelope(BaseModel):
    kind: ObservationEvidenceKind
    summary: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class ObservationRecord(BaseModel):
    topic: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    success: bool
    failure_stage: ObservationFailureStage | None = None
    evidence: list[EvidenceEnvelope] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GovernanceEvidenceDigest(BaseModel):
    total_observations: int = 0
    failure_stage_counts: dict[str, int] = Field(default_factory=dict)
    topic_failure_stage_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    observation_samples: list[ObservationRecord] = Field(default_factory=list)
