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
from typing import Any


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
        actions: List of supported actions
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
    actions: list[str] = field(default_factory=list)

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
            "actions": self.actions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillMeta":
        return cls(
            skill_id=data.get("skill_id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            detail_description=data.get("detail_description", ""),
            model_profile=data.get("model_profile", "balanced"),
            capability_level=data.get("capability_level", "L1"),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            permission_required=data.get("permission_required", "user"),
            tags=data.get("tags", []),
            actions=data.get("actions", []),
        )
