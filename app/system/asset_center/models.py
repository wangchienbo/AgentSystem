from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
            "model_requirement": {
                "preferred_model": self.model_requirement.preferred_model,
                "fallback_model": self.model_requirement.fallback_model,
                "minimum_requirements": self.model_requirement.minimum_requirements,
            },
            "metadata": self.metadata,
        }
