from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationResponseEnvelope


@dataclass(frozen=True)
class InvocationAuditRecord:
    request_id: str
    target_id: str
    method: str
    request_envelope: dict[str, Any]
    binding_resolution_mode: str | None = None
    resolved_local_session_id: str | None = None
    downstream_call_links: list[dict[str, Any]] = field(default_factory=list)
    tool_vllm_usage_links: list[dict[str, Any]] = field(default_factory=list)
    response: dict[str, Any] = field(default_factory=dict)


class InvocationAuditStore:
    def __init__(self) -> None:
        self._records: list[InvocationAuditRecord] = []

    def record(
        self,
        *,
        envelope: InvocationRequestEnvelope,
        response: InvocationResponseEnvelope | None = None,
        binding_resolution_mode: str | None = None,
        resolved_local_session_id: str | None = None,
        downstream_call_links: list[dict[str, Any]] | None = None,
        tool_vllm_usage_links: list[dict[str, Any]] | None = None,
    ) -> InvocationAuditRecord:
        record = InvocationAuditRecord(
            request_id=envelope.request_id,
            target_id=envelope.target_id,
            method=envelope.method,
            request_envelope=envelope.to_dict(),
            binding_resolution_mode=binding_resolution_mode,
            resolved_local_session_id=resolved_local_session_id,
            downstream_call_links=list(downstream_call_links or []),
            tool_vllm_usage_links=list(tool_vllm_usage_links or []),
            response={} if response is None else response.to_dict(),
        )
        self._records.append(record)
        return record

    def list_records(self) -> list[InvocationAuditRecord]:
        return list(self._records)

    def replay_chain(self, request_id: str) -> dict[str, Any]:
        matched = [item for item in self._records if item.request_id == request_id]
        if not matched:
            raise ValueError(f"audit record not found: {request_id}")
        record = matched[-1]
        return {
            "request_id": record.request_id,
            "target_id": record.target_id,
            "method": record.method,
            "binding_resolution_mode": record.binding_resolution_mode,
            "resolved_local_session_id": record.resolved_local_session_id,
            "request_envelope": record.request_envelope,
            "downstream_call_links": record.downstream_call_links,
            "tool_vllm_usage_links": record.tool_vllm_usage_links,
            "response": record.response,
        }
