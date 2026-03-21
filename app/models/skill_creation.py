from __future__ import annotations

from typing import Literal, Any

from pydantic import BaseModel, Field

from app.models.skill_control import SkillCapabilityProfile
from app.models.skill_runtime import SkillExecutionResult


class SkillSchemaDefinition(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)


class SkillCreationRequest(BaseModel):
    skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    adapter_kind: Literal["callable", "script"] = "script"
    generation_operation: str = Field(default="")
    handler_entry: str = Field(default="")
    command: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    capability_profile: SkillCapabilityProfile = Field(default_factory=SkillCapabilityProfile)
    schemas: SkillSchemaDefinition = Field(default_factory=SkillSchemaDefinition)
    smoke_test_inputs: dict[str, Any] = Field(default_factory=dict)


class SkillCreationResult(BaseModel):
    skill_id: str
    created: bool = True
    registered: bool = True
    schema_refs: dict[str, str] = Field(default_factory=dict)
    runtime_adapter: str
    smoke_test: SkillExecutionResult


class StepMappingDefinition(BaseModel):
    from_step: str = Field(default="")
    from_inputs: str = Field(default="")
    field: str = Field(default="")
    target_field: str = Field(..., min_length=1)
    transform: str = Field(default="")
    default_value: Any | None = None


class AppFromSkillsRequest(BaseModel):
    blueprint_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    goal: str = Field(default="run generated skills")
    skill_ids: list[str] = Field(default_factory=list)
    workflow_id: str = Field(default="wf.generated")
    step_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    step_mappings: dict[str, list[StepMappingDefinition]] = Field(default_factory=dict)


class AppFromSkillsResult(BaseModel):
    blueprint_id: str
    workflow_id: str
    required_skills: list[str] = Field(default_factory=list)
    created_steps: list[str] = Field(default_factory=list)


class AppFromSkillsInstallRunRequest(AppFromSkillsRequest):
    user_id: str = Field(..., min_length=1)
    workflow_inputs: dict[str, Any] = Field(default_factory=dict)
    trigger: str = Field(default="manual")
