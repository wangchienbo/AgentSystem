from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.system.invocation.invocation_audit import InvocationAuditStore
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationResponseEnvelope
from app.system.invocation.runtime_topology import RuntimeTopologyReadModel


@dataclass(frozen=True)
class ValidationHarnessResult:
    topology: dict[str, Any]
    replay: dict[str, Any]


class InvocationValidationHarness:
    def __init__(self, *, topology: RuntimeTopologyReadModel, audit_store: InvocationAuditStore) -> None:
        self._topology = topology
        self._audit_store = audit_store

    def validate_invocation_chain(
        self,
        *,
        envelope: InvocationRequestEnvelope,
        response: InvocationResponseEnvelope,
        binding_resolution_mode: str,
        resolved_local_session_id: str,
        downstream_call_links: list[dict[str, Any]] | None = None,
        tool_vllm_usage_links: list[dict[str, Any]] | None = None,
    ) -> ValidationHarnessResult:
        self._audit_store.record(
            envelope=envelope,
            response=response,
            binding_resolution_mode=binding_resolution_mode,
            resolved_local_session_id=resolved_local_session_id,
            downstream_call_links=downstream_call_links,
            tool_vllm_usage_links=tool_vllm_usage_links,
        )
        topology = self._topology.build_snapshot().to_dict()
        replay = self._audit_store.replay_chain(envelope.request_id)
        return ValidationHarnessResult(topology=topology, replay=replay)
