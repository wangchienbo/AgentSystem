from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AppControlSkillManifest(BaseModel):
    """Manifest for a generated app-level control skill."""
    skill_id: str
    name: str
    description: str
    version: str = "1.0.0"
    handler_entry: str = ""
    tags: list[str] = Field(default_factory=list)
    capability_profile: dict[str, Any] = Field(default_factory=dict)


class SubordinateSkillSuggestion(BaseModel):
    """A suggested subordinate skill for the app."""
    suggested_name: str
    scope: str
    responsibility: str
    priority: str = "medium"  # high / medium / low


class AppControlSkillResult(BaseModel):
    """Full output of the meta-app control skill generator."""
    app_name: str
    app_slug: str
    anchor_file: str
    control_skill: AppControlSkillManifest
    subordinate_suggestions: list[SubordinateSkillSuggestion] = Field(default_factory=list)
    decomposition_plan: list[str] = Field(default_factory=list)
    governance_notes: list[str] = Field(default_factory=list)
