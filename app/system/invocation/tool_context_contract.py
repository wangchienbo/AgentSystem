from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolContextQueryRequest:
    asset_id: str
    local_session_id: str
    purpose: str = "model_inference"
    query: str = ""
    recent_limit: int = 20
    include_summary: bool = True
    include_snapshot: bool = True
    include_evidence_refs: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.asset_id.strip():
            raise ValueError("asset_id is required")
        if not self.local_session_id.strip():
            raise ValueError("local_session_id is required")
        if self.recent_limit < 1:
            raise ValueError("recent_limit must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "local_session_id": self.local_session_id,
            "purpose": self.purpose,
            "query": self.query,
            "recent_limit": self.recent_limit,
            "include_summary": self.include_summary,
            "include_snapshot": self.include_snapshot,
            "include_evidence_refs": self.include_evidence_refs,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ToolContextQueryResponse:
    asset_id: str
    local_session_id: str
    recent_records: list[dict[str, Any]] = field(default_factory=list)
    summary_records: list[dict[str, Any]] = field(default_factory=list)
    snapshot_record: dict[str, Any] | None = None
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    trace_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "local_session_id": self.local_session_id,
            "recent_records": self.recent_records,
            "summary_records": self.summary_records,
            "snapshot_record": self.snapshot_record,
            "evidence_refs": self.evidence_refs,
            "trace_metadata": self.trace_metadata,
        }


@dataclass(frozen=True)
class ModelInvocationRecord:
    request_id: str
    asset_id: str
    local_session_id: str
    model_id: str
    context_refs: list[str] = field(default_factory=list)
    token_usage: dict[str, Any] = field(default_factory=dict)
    output_summary: str = ""
    trace_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "asset_id": self.asset_id,
            "local_session_id": self.local_session_id,
            "model_id": self.model_id,
            "context_refs": self.context_refs,
            "token_usage": self.token_usage,
            "output_summary": self.output_summary,
            "trace_metadata": self.trace_metadata,
        }
