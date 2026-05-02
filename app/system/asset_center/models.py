from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


INVOCATION_ERROR_TYPES = {
    "routing_error",
    "binding_error",
    "context_error",
    "invocation_error",
    "runtime_error",
    "model_error",
    "persistence_error",
}


@dataclass(frozen=True)
class AssetMethodSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetModelRequirement:
    preferred_model: str | None = None
    fallback_model: str | None = None
    minimum_requirements: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_model": self.preferred_model,
            "fallback_model": self.fallback_model,
            "minimum_requirements": self.minimum_requirements,
        }


@dataclass(frozen=True)
class InteractionDecisionEnvelope:
    decision: str
    text: str | None = None
    need_asset_detail_id: str | None = None
    invoke: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        allowed = {"text", "need_asset_detail_id", "invoke"}
        if self.decision not in allowed:
            raise ValueError(f"decision must be one of {sorted(allowed)}")
        if self.decision == "text" and not self.text:
            raise ValueError("text decision requires text")
        if self.decision == "need_asset_detail_id" and not self.need_asset_detail_id:
            raise ValueError("need_asset_detail_id decision requires need_asset_detail_id")
        if self.decision == "invoke" and not self.invoke:
            raise ValueError("invoke decision requires invoke payload")

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "text": self.text,
            "need_asset_detail_id": self.need_asset_detail_id,
            "invoke": self.invoke,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AssetSessionBindingRecord:
    asset_id: str
    upstream_session_id: str
    local_session_id: str
    root_session_id: str | None = None
    parent_session_id: str | None = None
    status: str = "active"
    created_at: str = ""
    last_active_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.asset_id.strip():
            raise ValueError("asset_id is required")
        if not self.upstream_session_id.strip():
            raise ValueError("upstream_session_id is required")
        if not self.local_session_id.strip():
            raise ValueError("local_session_id is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "upstream_session_id": self.upstream_session_id,
            "local_session_id": self.local_session_id,
            "root_session_id": self.root_session_id,
            "parent_session_id": self.parent_session_id,
            "status": self.status,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AssetDescriptorRecord:
    descriptor_version: int
    asset_id: str
    kind: str
    summary: str
    detail: str
    methods: tuple[AssetMethodSpec, ...] = field(default_factory=tuple)
    model_requirement: AssetModelRequirement = field(default_factory=AssetModelRequirement)
    metadata: dict[str, Any] = field(default_factory=dict)
    registration_epoch: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "descriptor_version": self.descriptor_version,
            "asset_id": self.asset_id,
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail,
            "methods": [
                {
                    "name": method.name,
                    "description": method.description,
                    "input_schema": method.input_schema,
                    "output_schema": method.output_schema,
                }
                for method in self.methods
            ],
            "model_requirement": self.model_requirement.to_dict(),
            "metadata": self.metadata,
            "registration_epoch": self.registration_epoch,
        }
