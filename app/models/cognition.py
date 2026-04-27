from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SelfModel(BaseModel):
    """Machine-readable self-awareness state for bounded cognition."""

    role_identity: str = Field(default="agent_system_gateway")
    mission: str = Field(default="evidence-bound cognition and action")
    capability_state: Literal["direct", "tool_required", "verification_required", "unknown"] = Field(default="unknown")
    tool_dependence_state: Literal["none", "optional", "required"] = Field(default="required")
    boundary_state: Literal["within_policy", "clarification_required", "blocked"] = Field(default="within_policy")
    confidence_state: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertainty_state: str = Field(default="")
    policy_state: str = Field(default="evidence_first")
    human_equivalence_state: Literal["non_human_equivalent"] = Field(default="non_human_equivalent")
    answer_mode: Literal["direct", "tool_required", "verification_required", "clarification_required"] = Field(default="direct")
    verification_mode: Literal["none", "light", "required"] = Field(default="none")


class StructuredClaim(BaseModel):
    """A bounded claim produced from available evidence."""

    text: str = Field(default="")
    evidence_grade: Literal["none", "hint", "excerpt", "verified_fact", "runtime_observation"] = Field(default="none")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class StructuredAnswer(BaseModel):
    """Structured introspection-style answer contract."""

    self_model: SelfModel
    claim: StructuredClaim
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    unverified_points: list[str] = Field(default_factory=list)
    text: str = Field(default="")
