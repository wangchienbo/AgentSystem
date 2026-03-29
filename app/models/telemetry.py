from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CollectionLevel = Literal["off", "light", "medium", "heavy", "custom"]
TelemetryStepType = Literal["reason", "tool", "skill", "subagent", "system"]
FeedbackKind = Literal["explicit", "implicit"]
CollectionPolicyScope = Literal["global", "app", "skill", "agent", "task_type"]


class InteractionTelemetryRecord(BaseModel):
    interaction_id: str = Field(..., min_length=1)
    session_id: str | None = None
    user_id: str | None = None
    app_id: str | None = None
    app_version: str | None = None
    agent_id: str | None = None
    agent_version: str | None = None
    request_type: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    success: bool = True
    failure_reason: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_latency_ms: int = 0
    total_tool_calls: int = 0
    strategy_name: str | None = None
    collection_level: CollectionLevel = "light"
    aborted: bool = False
    retried: bool = False
    escalated: bool = False


class StepTelemetryRecord(BaseModel):
    interaction_id: str = Field(..., min_length=1)
    step_id: str = Field(..., min_length=1)
    parent_step_id: str | None = None
    step_type: TelemetryStepType
    name: str = Field(..., min_length=1)
    version: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    success: bool = True
    error_code: str | None = None
    retry_count: int = 0
    cache_hit: bool = False
    estimated_cost: float = 0.0
    payload_summary: dict[str, Any] | None = None


class FeedbackRecord(BaseModel):
    feedback_id: str = Field(..., min_length=1)
    interaction_id: str = Field(..., min_length=1)
    scope_type: Literal["app", "skill", "session", "interaction"]
    scope_id: str = Field(..., min_length=1)
    feedback_kind: FeedbackKind
    score: int | None = None
    labels: list[str] = Field(default_factory=list)
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VersionBindingRecord(BaseModel):
    interaction_id: str = Field(..., min_length=1)
    app_version: str | None = None
    skill_versions: dict[str, str] = Field(default_factory=dict)
    agent_version: str | None = None
    policy_version: str | None = None
    evaluation_suite_version: str | None = None


class CollectionPolicyRecord(BaseModel):
    scope_type: CollectionPolicyScope
    scope_id: str = Field(..., min_length=1)
    enabled: bool = True
    level: CollectionLevel = "light"
    capture_feedback: bool = True
    capture_payload_summary: bool = False
    capture_truncated_payload: bool = False
    allow_skill_extension: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
