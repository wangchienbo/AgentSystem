"""App instance binding — Orchestrator + Skill Worker configuration.

Defines which skill workers are bound to an app instance and how they
are configured (enabled, custom config, log level overrides).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.log_center import LogCollectionConfig, LogLevel


class SkillBindingConfig(BaseModel):
    """Binding config for a single skill in an app."""

    skill_id: str = Field(..., min_length=1)
    enabled: bool = True
    custom_config: dict[str, Any] = Field(default_factory=dict)
    log_level: LogLevel | None = Field(default=None, description="Override global log level")


class AppInstanceBinding(BaseModel):
    """Complete binding config for an app instance.

    One app instance = 1 Orchestrator + N skill bindings.
    Skill workers can be shared across multiple app instances.
    """

    app_instance_id: str = Field(..., min_length=1)
    orchestrator_id: str = Field(default="orchestrator")
    skill_bindings: dict[str, SkillBindingConfig] = Field(default_factory=dict)
    log_config: LogCollectionConfig = Field(default_factory=LogCollectionConfig)

    def bind_skill(self, skill_id: str, config: SkillBindingConfig | None = None) -> None:
        """Bind a skill to this app."""
        self.skill_bindings[skill_id] = config or SkillBindingConfig(skill_id=skill_id)

    def unbind_skill(self, skill_id: str) -> bool:
        if skill_id in self.skill_bindings:
            del self.skill_bindings[skill_id]
            return True
        return False

    def is_bound(self, skill_id: str) -> bool:
        binding = self.skill_bindings.get(skill_id)
        return binding is not None and binding.enabled

    def get_log_level(self, skill_id: str) -> LogLevel:
        """Get effective log level for a skill."""
        binding = self.skill_bindings.get(skill_id)
        if binding and binding.log_level:
            return binding.log_level
        return self.log_config.level

    def get_bound_skills(self) -> list[str]:
        return [
            sid for sid, cfg in self.skill_bindings.items()
            if cfg.enabled
        ]
