"""Data models for App Design/Creation flow (Phase F.3)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# -- Intent Analysis Models --------------------------------------------------


class AppIntentResult(BaseModel):
    """Result of app creation intent analysis."""
    app_name: str = Field(default="", description="Suggested app name")
    goal: str = Field(default="", description="One-sentence core objective")
    kind: Literal["interactive", "service", "scheduled", "monitoring"] = Field(default="service")
    complexity: Literal["simple", "moderate", "complex"] = Field(default="moderate")
    constraints: list[str] = Field(default_factory=list)
    needs_clarification: bool = Field(default=False)
    clarification_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# -- Architecture Design Models ----------------------------------------------


class SubordinateSkillDesign(BaseModel):
    """Design for a subordinate skill."""
    suggested_name: str
    scope: str
    responsibility: str
    priority: Literal["high", "medium", "low"] = "medium"
    reuse_existing: str | None = None  # If reusing an existing skill, its ID


class AppDesignResult(BaseModel):
    """Result of app architecture design."""
    app_name: str
    app_slug: str
    control_skill_name: str
    control_skill_description: str
    subordinate_skills: list[SubordinateSkillDesign] = Field(default_factory=list)
    reused_skills: list[str] = Field(default_factory=list)  # Skill IDs being reused
    new_skills: list[str] = Field(default_factory=list)  # Skill IDs to be created
    decomposition_plan: list[str] = Field(default_factory=list)
    governance_notes: list[str] = Field(default_factory=list)
    design_notes: str = ""


# -- User Confirmation Models ------------------------------------------------


class DesignConfirmation(BaseModel):
    """User confirmation of app design."""
    approved: bool
    feedback: str = Field(default="", description="User feedback if rejected or needs changes")
    modifications: dict[str, Any] = Field(default_factory=dict)  # User-requested modifications


# -- Orchestration Models ----------------------------------------------------


AppCreationStatus = Literal[
    "needs_clarification",
    "needs_confirmation",
    "approved",
    "rejected_by_user",
    "success",
    "failed",
]


class AppCreationResult(BaseModel):
    """End-to-end app creation result."""
    status: AppCreationStatus
    app_name: str = ""
    design: AppDesignResult | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    created_skill_ids: list[str] = Field(default_factory=list)
    error: str = ""
    message: str = ""
