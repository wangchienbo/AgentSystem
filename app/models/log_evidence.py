from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.operator_contracts import OperatorPageMeta

EvidenceCategory = Literal["workflow_failure", "policy_pressure", "clarify_unresolved"]
EvidenceSeverity = Literal["low", "medium", "high"]
EvidenceStatus = Literal["draft", "suspicious", "promoted"]


class RawLogRef(BaseModel):
    ref_id: str = Field(default_factory=lambda: f"raw-{uuid4().hex[:12]}")
    source_type: str
    source_id: str
    app_instance_id: str | None = None
    workflow_id: str | None = None
    skill_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DraftSummary(BaseModel):
    draft_id: str = Field(default_factory=lambda: f"draft-{uuid4().hex[:12]}")
    category: EvidenceCategory
    scope_key: str
    app_instance_id: str | None = None
    workflow_id: str | None = None
    skill_id: str | None = None
    summary: str
    event_count: int = 0
    supporting_ref_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SuspiciousSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: f"signal-{uuid4().hex[:12]}")
    category: EvidenceCategory
    severity: EvidenceSeverity = "medium"
    status: EvidenceStatus = "suspicious"
    scope_key: str
    app_instance_id: str | None = None
    workflow_id: str | None = None
    skill_id: str | None = None
    reason: str
    supporting_ref_ids: list[str] = Field(default_factory=list)
    frequency: int = 1
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromotedEvidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"evidence-{uuid4().hex[:12]}")
    category: EvidenceCategory
    source_signal_id: str
    scope_key: str
    app_instance_id: str | None = None
    workflow_id: str | None = None
    skill_id: str | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    summary: str
    impact_area: str = "runtime"
    recommended_action: str = "review"
    supporting_ref_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RetrievalIndexEntry(BaseModel):
    index_id: str = Field(default_factory=lambda: f"index-{uuid4().hex[:12]}")
    source_type: Literal["signal", "evidence"]
    source_id: str
    topic: str
    scope_key: str
    app_instance_id: str | None = None
    workflow_id: str | None = None
    skill_id: str | None = None
    short_summary: str
    keywords: list[str] = Field(default_factory=list)
    priority: int = 0
    freshness_ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidencePage(BaseModel):
    items: list[Any] = Field(default_factory=list)
    meta: OperatorPageMeta = Field(default_factory=OperatorPageMeta)
