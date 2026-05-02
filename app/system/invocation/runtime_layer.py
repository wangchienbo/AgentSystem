from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from app.system.asset_center.models import AssetSessionBindingRecord
from app.system.asset_center.service import AssetCenterService
from app.system.invocation.invocation_envelope import InvocationRequestEnvelope, InvocationResponseEnvelope


@dataclass(frozen=True)
class BindingResolution:
    local_session_id: str
    mode: str
    binding: AssetSessionBindingRecord

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_session_id": self.local_session_id,
            "mode": self.mode,
            "binding": self.binding.to_dict(),
        }


class AssetInvocationRuntimeLayer:
    def __init__(
        self,
        *,
        asset_center: AssetCenterService,
        historical_session_resolver: Callable[[InvocationRequestEnvelope], str | None] | None = None,
    ) -> None:
        self._asset_center = asset_center
        self._historical_session_resolver = historical_session_resolver
        self._binding_cache: dict[tuple[str, str], AssetSessionBindingRecord] = {}

    def before_invoke(self, envelope: InvocationRequestEnvelope) -> BindingResolution:
        envelope.validate()
        return self.resolve_local_session(envelope)

    def resolve_local_session(self, envelope: InvocationRequestEnvelope) -> BindingResolution:
        session = envelope.session
        if session is None or not session.upstream_session_id.strip():
            binding = self._build_new_binding(envelope, upstream_session_id=f"request:{envelope.request_id}")
            self.persist_binding(binding)
            return BindingResolution(local_session_id=binding.local_session_id, mode="new", binding=binding)

        key = (envelope.target_id, session.upstream_session_id)
        cached = self._binding_cache.get(key)
        if cached is not None:
            return BindingResolution(local_session_id=cached.local_session_id, mode="memory", binding=cached)

        persisted = self._asset_center.get_session_binding(envelope.target_id, session.upstream_session_id)
        if persisted is not None:
            self._binding_cache[key] = persisted
            return BindingResolution(local_session_id=persisted.local_session_id, mode="persisted", binding=persisted)

        recovered_session_id = None
        if self._historical_session_resolver is not None:
            recovered_session_id = self._historical_session_resolver(envelope)
        if recovered_session_id:
            binding = self._build_new_binding(
                envelope,
                upstream_session_id=session.upstream_session_id,
                local_session_id=recovered_session_id,
            )
            persisted_binding = self.persist_binding(binding)
            return BindingResolution(
                local_session_id=persisted_binding.local_session_id,
                mode="recovered_by_history",
                binding=persisted_binding,
            )

        binding = self._build_new_binding(envelope, upstream_session_id=session.upstream_session_id)
        persisted_binding = self.persist_binding(binding)
        return BindingResolution(local_session_id=persisted_binding.local_session_id, mode="new", binding=persisted_binding)

    def persist_binding(self, record: AssetSessionBindingRecord) -> AssetSessionBindingRecord:
        stored = self._asset_center.upsert_session_binding(record)
        self._binding_cache[(stored.asset_id, stored.upstream_session_id)] = stored
        return stored

    def after_invoke(
        self,
        envelope: InvocationRequestEnvelope,
        response: InvocationResponseEnvelope,
        resolution: BindingResolution,
    ) -> InvocationResponseEnvelope:
        metadata = dict(response.metadata)
        metadata.setdefault("binding", resolution.to_dict())
        metadata.setdefault("request_id", envelope.request_id)
        return InvocationResponseEnvelope(
            ok=response.ok,
            request_id=response.request_id,
            data=response.data,
            error=response.error,
            error_type=response.error_type,
            error_taxonomy=response.error_taxonomy,
            resolved_local_session_id=resolution.local_session_id,
            trace_context=response.trace_context,
            state_updates=response.state_updates,
            metadata=metadata,
        )

    def _build_new_binding(
        self,
        envelope: InvocationRequestEnvelope,
        *,
        upstream_session_id: str,
        local_session_id: str | None = None,
    ) -> AssetSessionBindingRecord:
        root_session_id = envelope.session.root_session_id if envelope.session is not None else None
        parent_session_id = envelope.session.parent_session_id if envelope.session is not None else None
        return AssetSessionBindingRecord(
            asset_id=envelope.target_id,
            upstream_session_id=upstream_session_id,
            local_session_id=local_session_id or f"{envelope.target_id}:{uuid4().hex}",
            root_session_id=root_session_id,
            parent_session_id=parent_session_id,
            status="active",
            metadata={"request_id": envelope.request_id},
        )
