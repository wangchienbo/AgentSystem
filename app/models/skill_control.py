from __future__ import annotations

from datetime import datetime, UTC
from typing import Literal

from pydantic import BaseModel, Field

from app.models.skill_manifest import SkillManifest

SkillStatus = Literal["active", "disabled", "rollback_ready"]
SkillIntelligenceLevel = Literal["L0_deterministic", "L1_assisted", "L2_semantic", "L3_autonomous"]
SkillNetworkRequirement = Literal["N0_none", "N1_optional", "N2_required"]
SkillRuntimeCriticality = Literal["C0_build_only", "C1_optional_runtime", "C2_required_runtime", "build_and_runtime_governance", "build_only_or_optional_runtime"]
SkillExecutionLocality = Literal["local", "hybrid", "remote"]
SkillInvocationDefault = Literal["automatic", "ask_user", "explicit_only"]


class SkillCapabilityProfile(BaseModel):
    intelligence_level: SkillIntelligenceLevel = "L0_deterministic"
    network_requirement: SkillNetworkRequirement = "N0_none"
    runtime_criticality: SkillRuntimeCriticality = "C2_required_runtime"
    execution_locality: SkillExecutionLocality = "local"
    invocation_default: SkillInvocationDefault = "automatic"
    risk_level: str = Field(default="R0_safe_read", min_length=1)


class SkillVersion(BaseModel):
    version: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str = Field(default="")


class SkillRegistryEntry(BaseModel):
    skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    immutable_interface: bool = False
    status: SkillStatus = "active"
    active_version: str = Field(..., min_length=1)
    versions: list[SkillVersion] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    capability_profile: SkillCapabilityProfile = Field(default_factory=SkillCapabilityProfile)
    runtime_adapter: str = Field(default="callable", min_length=1)
    manifest: SkillManifest | None = None


class SkillMutationResult(BaseModel):
    skill_id: str
    action: Literal["replace", "rollback", "disable", "enable"]
    status: SkillStatus
    active_version: str
