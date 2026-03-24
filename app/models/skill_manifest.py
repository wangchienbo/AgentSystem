from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.skill_adapter import SkillAdapterSpec


class SkillContractRef(BaseModel):
    input_schema_ref: str = Field(default="")
    output_schema_ref: str = Field(default="")
    error_schema_ref: str = Field(default="")


class SkillManifestRisk(BaseModel):
    risk_level: str = Field(default="R0_safe_read", min_length=1)
    allow_network: bool = False
    allow_filesystem_write: bool = False
    allow_shell: bool = False


class SkillManifest(BaseModel):
    skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    description: str = Field(default="")
    runtime_adapter: str = Field(default="callable", min_length=1)
    adapter: SkillAdapterSpec = Field(default_factory=SkillAdapterSpec)
    contract: SkillContractRef = Field(default_factory=SkillContractRef)
    tags: list[str] = Field(default_factory=list)
    risk: SkillManifestRisk = Field(default_factory=SkillManifestRisk)
