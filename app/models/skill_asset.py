from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


AssetStatus = Literal["draft", "candidate", "core", "deprecated", "archived"]
AssetOrigin = Literal["handwritten", "generated", "refined", "imported"]
ContentMaturity = Literal["scaffold", "prototype", "functional", "production_ready"]
RuntimeAdapter = Literal["callable", "script", "executable"]


class SkillAssetMetadata(BaseModel):
    skill_id: str = Field(..., min_length=1)
    asset_slug: str = Field(..., min_length=1)
    asset_status: AssetStatus = "candidate"
    asset_origin: AssetOrigin = "generated"
    runtime_adapter: RuntimeAdapter = "executable"
    version: str = Field(default="0.1.0", min_length=1)
    content_maturity: ContentMaturity = "scaffold"
    accepted: bool = False
    accepted_at: str | None = None
    accepted_by: str | None = None
    source_template: str | None = None
    source_workflow: str | None = None
    source_experience_id: str | None = None
    promoted_from: str | None = None
    archived_from: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class SkillAssetIndexEntry(BaseModel):
    skill_id: str
    asset_slug: str
    asset_status: AssetStatus
    asset_origin: AssetOrigin
    runtime_adapter: RuntimeAdapter
    version: str
    content_maturity: ContentMaturity
    path: str
    manifest_path: str
    metadata_path: str
    accepted: bool = False
    accepted_at: str | None = None


class SkillAssetIndex(BaseModel):
    version: int = 1
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    assets: list[SkillAssetIndexEntry] = Field(default_factory=list)


class SkillAssetConsistencyIssue(BaseModel):
    kind: str
    message: str
    details: dict = Field(default_factory=dict)


class SkillAssetConsistencyResult(BaseModel):
    skill_id: str
    ok: bool = True
    issues: list[SkillAssetConsistencyIssue] = Field(default_factory=list)
