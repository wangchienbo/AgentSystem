"""Skill metadata — input/output schemas and action definitions.

Provides structured metadata that App creators use to discover, compose,
and validate skill usage in an App blueprint.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ActionMeta(BaseModel):
    """Metadata for a single skill action."""

    name: str = Field(..., min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_default: float = 30.0
    retry_default: int = 1


class SkillMetaInfo(BaseModel):
    """Complete metadata for a Skill, used by App creators for composition."""

    skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    version: str = "1.0.0"

    # 输入输出格式（创作者组装时的关键信息）
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)

    # 多接口定义
    actions: dict[str, ActionMeta] = Field(default_factory=dict)

    # 依赖与能力
    dependencies: list[str] = Field(default_factory=list)
    offline_capable: bool = False
    risk_level: str = "R0_safe_read"
    network_requirement: str = "N0_none"

    # 调试与溯源
    author: str = ""
    source: str = "builtin"  # "builtin" | "remote" | "created"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def summary(self) -> dict[str, Any]:
        """Short summary for creator UI."""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "actions": list(self.actions.keys()),
            "offline_capable": self.offline_capable,
            "dependencies": self.dependencies,
        }

    def compatible_with(self, upstream_output_schema: dict) -> bool:
        """Check if this skill's input can accept upstream output."""
        if not self.input_schema:
            return True  # no constraints
        required = self.input_schema.get("required", [])
        upstream_props = upstream_output_schema.get("properties", {})
        return all(field in upstream_props for field in required)
