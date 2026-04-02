from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class GeneratedSkillRequest(BaseModel):
    skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    language: str = Field(default="python", min_length=1)
    template_type: str = Field(default="text_transform", min_length=1)


class GeneratedSkillAsset(BaseModel):
    skill_id: str = Field(..., min_length=1)
    asset_dir: str = Field(..., min_length=1)
    manifest_path: str = Field(..., min_length=1)
    schema_path: str = Field(..., min_length=1)
    input_schema_path: str = Field(default="", min_length=0)
    output_schema_path: str = Field(default="", min_length=0)
    error_schema_path: str = Field(default="", min_length=0)
    entrypoint_path: str = Field(..., min_length=1)
    readme_path: str = Field(..., min_length=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
