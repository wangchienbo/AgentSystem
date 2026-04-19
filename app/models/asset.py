"""Runtime asset model compatibility layer.

Keeps older asset-registry callers working while exposing the new Phase H
formal contract fields through AssetDescriptor / AssetCapability / AssetState.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.asset_contract import (
    AssetCapability,
    AssetDescriptor,
    AssetKind,
    AssetState,
    AssetType,
    Visibility,
)


@dataclass
class AssetFunction:
    """Backward-compatible callable function surface for existing code."""

    key: str
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    permission_hint: str = ""
    side_effect_level: str = "read"
    requires_runtime_alive: bool = True

    def to_capability(self) -> AssetCapability:
        return AssetCapability(
            name=self.name,
            description=self.description,
            method=self.key,
            input_schema_ref=self.input_schema.get("$ref") if isinstance(self.input_schema, dict) else None,
            output_schema_ref=self.output_schema.get("$ref") if isinstance(self.output_schema, dict) else None,
            side_effect_level=self.side_effect_level if self.side_effect_level in {"none", "read", "write", "admin"} else "read",
            requires_runtime_alive=self.requires_runtime_alive,
            permission_hint=self.permission_hint or None,
            metadata={
                "input_schema": self.input_schema,
                "output_schema": self.output_schema,
                "notes": self.notes,
            },
        )


@dataclass
class Asset:
    """Backward-compatible runtime asset with Phase H descriptor semantics."""

    asset_id: str
    asset_type: AssetType
    owner_id: str
    name: str
    description: str
    visibility: Visibility = Visibility.PRIVATE
    functions: list[AssetFunction] = field(default_factory=list)
    shared_with: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_running: bool = True
    version: str = "0.0.0"
    owner_type: str = "user"
    source_of_truth: str = "runtime"
    asset_kind: AssetKind = AssetKind.MATERIALIZED
    status: AssetState = AssetState.ACTIVE
    invoke_contract: dict[str, Any] = field(default_factory=dict)
    health_contract: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    def add_function(self, fn: AssetFunction) -> None:
        self.functions.append(fn)

    def get_function(self, key: str) -> AssetFunction | None:
        for f in self.functions:
            if f.key == key:
                return f
        return None

    def overview(self) -> str:
        fn_names = ", ".join(f.name for f in self.functions)
        return f"- {self.asset_id}: [{fn_names}]"

    def to_descriptor(self) -> AssetDescriptor:
        metadata = dict(self.metadata)
        metadata.setdefault("shared_with", list(self.shared_with))
        return AssetDescriptor(
            asset_id=self.asset_id,
            asset_type=self.asset_type,
            asset_kind=self.asset_kind,
            version=self.version,
            owner_type=self.owner_type,
            owner_id=self.owner_id,
            source_of_truth=self.source_of_truth,
            status=self.status,
            capabilities=[fn.to_capability() for fn in self.functions],
            invoke_contract=self.invoke_contract,
            health_contract=self.health_contract,
            created_at=self.created_at,
            updated_at=self.updated_at,
            tags=list(self.tags),
            name=self.name,
            description=self.description,
            visibility=self.visibility,
            metadata=metadata,
        )
