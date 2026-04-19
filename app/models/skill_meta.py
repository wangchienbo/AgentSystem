"""Skill Meta Schema — standardized metadata for all skills.

Every skill in the AgentSystem must declare its meta information, including:
- Input/output schemas
- Default model profile (strong/balanced/fast)
- Capability level (L1/L2/L3)
- Permission requirements

This schema is used by:
1. App Designer to validate skill composition
2. ToolCallExecutor to determine model routing
3. AssetRegistry to generate L1/L2 descriptions
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ActionMeta:
    """Metadata for a single action within a skill."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    timeout_default: float = 30.0


@dataclass
class SkillMeta:
    """Metadata for a skill.

    Attributes:
        skill_id: Unique identifier (e.g. "skill.maoxuan")
        name: Human-readable name
        version: Semantic version string
        description: One-line summary (L1)
        detail_description: Detailed description (L2)
        model_profile: Default model profile (strong/balanced/fast)
        capability_level: L1 (basic) / L2 (detailed) / L3 (full)
        input_schema: JSON Schema for input parameters
        output_schema: JSON Schema for output
        permission_required: Minimum permission level
        tags: Categorization tags
        actions: Declared supported actions and metadata
    """

    skill_id: str
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    detail_description: str = ""
    model_profile: str = "balanced"  # strong | balanced | fast
    capability_level: str = "L1"  # L1 | L2 | L3
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    permission_required: str = "user"  # user | admin | root
    tags: list[str] = field(default_factory=list)
    actions: dict[str, ActionMeta] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    offline_capable: bool = False
    source: str = "builtin"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "detail_description": self.detail_description,
            "model_profile": self.model_profile,
            "capability_level": self.capability_level,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "permission_required": self.permission_required,
            "tags": self.tags,
            "actions": {
                name: {
                    "name": action.name,
                    "description": action.description,
                    "input_schema": action.input_schema,
                    "output_schema": action.output_schema,
                    "timeout_default": action.timeout_default,
                }
                for name, action in self.actions.items()
            },
            "dependencies": self.dependencies,
            "offline_capable": self.offline_capable,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillMeta":
        actions_raw = data.get("actions", {}) or {}
        if isinstance(actions_raw, list):
            actions = {
                name: ActionMeta(name=name)
                for name in actions_raw
                if isinstance(name, str)
            }
        else:
            actions = {
                name: ActionMeta(
                    name=payload.get("name", name),
                    description=payload.get("description", ""),
                    input_schema=payload.get("input_schema", {}) or {},
                    output_schema=payload.get("output_schema", {}) or {},
                    timeout_default=payload.get("timeout_default", payload.get("timeout", 30.0)),
                )
                for name, payload in actions_raw.items()
            }

        created_at = data.get("created_at")
        updated_at = data.get("updated_at")
        return cls(
            skill_id=data.get("skill_id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            detail_description=data.get("detail_description", ""),
            model_profile=data.get("model_profile", "balanced"),
            capability_level=data.get("capability_level", "L1"),
            input_schema=data.get("input_schema", {}) or {},
            output_schema=data.get("output_schema", {}) or {},
            permission_required=data.get("permission_required", "user"),
            tags=data.get("tags", []) or [],
            actions=actions,
            dependencies=data.get("dependencies", []) or [],
            offline_capable=bool(data.get("offline_capable", False)),
            source=data.get("source", "builtin"),
            created_at=datetime.fromisoformat(created_at) if isinstance(created_at, str) else datetime.now(UTC),
            updated_at=datetime.fromisoformat(updated_at) if isinstance(updated_at, str) else datetime.now(UTC),
        )

    def compatible_with(self, upstream_output_schema: dict[str, Any] | None) -> bool:
        """Basic compatibility check: required downstream fields must exist upstream."""

        downstream_required = self.input_schema.get("required", []) if isinstance(self.input_schema, dict) else []
        if not downstream_required:
            return True

        upstream_output_schema = upstream_output_schema or {}
        upstream_properties = upstream_output_schema.get("properties", {}) if isinstance(upstream_output_schema, dict) else {}
        if not upstream_properties and isinstance(upstream_output_schema, dict):
            upstream_properties = upstream_output_schema
        return all(field in upstream_properties for field in downstream_required)


# Backward-compat aliases (SkillMeta was renamed from SkillMetaInfo)
SkillMetaInfo = SkillMeta
