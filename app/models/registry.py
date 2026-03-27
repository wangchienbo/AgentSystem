from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.app_profile import AppRuntimeProfile

AppReleaseStatus = Literal["draft", "active", "superseded", "rolled_back"]

RegistryStatus = Literal["draft", "registered", "deprecated", "archived"]
InstallStatus = Literal["installed", "upgraded"]


class AppReleaseRecord(BaseModel):
    version: str = Field(..., min_length=1)
    status: AppReleaseStatus = "active"
    note: str = ""
    reviewer: str = ""
    approved_at: datetime | None = None
    rollback_reason: str = ""
    app_shape: str = "generic"
    required_skills: list[str] = Field(default_factory=list)
    runtime_policy: dict = Field(default_factory=dict)
    runtime_profile: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppReleaseComparison(BaseModel):
    blueprint_id: str
    from_version: str
    to_version: str
    active_version: str
    active_is_from: bool = False
    active_is_to: bool = False
    from_status: AppReleaseStatus = "draft"
    to_status: AppReleaseStatus = "draft"
    from_note: str = ""
    to_note: str = ""
    from_reviewer: str = ""
    to_reviewer: str = ""
    from_created_at: datetime | None = None
    to_created_at: datetime | None = None
    release_note_changed: bool = False
    required_skills_changed: bool = False
    runtime_policy_changed: bool = False
    runtime_profile_changed: bool = False
    app_shape_changed: bool = False
    required_skills_added: list[str] = Field(default_factory=list)
    required_skills_removed: list[str] = Field(default_factory=list)
    runtime_policy_changes: dict[str, dict[str, object | None]] = Field(default_factory=dict)
    runtime_profile_changes: dict[str, dict[str, object | None]] = Field(default_factory=dict)
    app_shape_from: str = "generic"
    app_shape_to: str = "generic"
    change_count: int = 0
    changed_fields: list[str] = Field(default_factory=list)
    summary: str = ""


class AppRegistryEntry(BaseModel):
    blueprint_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    status: RegistryStatus = "registered"
    description: str = ""
    release_status: AppReleaseStatus = "active"
    release_note: str = ""
    reviewer: str = ""
    approved_at: datetime | None = None
    rollback_reason: str = ""
    releases: list[AppReleaseRecord] = Field(default_factory=list)
    app_shape: str = Field(default="generic")
    runtime_profile_summary: AppRuntimeProfile = Field(default_factory=AppRuntimeProfile)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppReleaseHistorySummary(BaseModel):
    blueprint_id: str
    active_version: str
    active_release_status: AppReleaseStatus = "active"
    total_releases: int = 0
    draft_release_count: int = 0
    superseded_release_count: int = 0
    rolled_back_release_count: int = 0
    latest_release_version: str = ""
    latest_release_created_at: datetime | None = None
    latest_draft_version: str | None = None
    latest_draft_created_at: datetime | None = None
    rollback_target_version: str | None = None
    releases: list[AppReleaseRecord] = Field(default_factory=list)


class AppControlPlaneSummary(BaseModel):
    blueprint_id: str
    name: str
    description: str = ""
    status: RegistryStatus = "registered"
    active_version: str
    active_release_status: AppReleaseStatus = "active"
    app_shape: str = "generic"
    runtime_profile: AppRuntimeProfile = Field(default_factory=AppRuntimeProfile)
    total_releases: int = 0
    draft_release_count: int = 0
    superseded_release_count: int = 0
    rolled_back_release_count: int = 0
    latest_release_version: str = ""
    latest_release_created_at: datetime | None = None
    latest_draft_version: str | None = None
    rollback_target_version: str | None = None
    rollback_available: bool = False
    release_note: str = ""
    reviewer: str = ""
    approved_at: datetime | None = None


class AppRegistryOverviewItem(BaseModel):
    blueprint_id: str
    name: str
    active_version: str
    active_release_status: AppReleaseStatus = "active"
    app_shape: str = "generic"
    runtime_profile: AppRuntimeProfile = Field(default_factory=AppRuntimeProfile)
    total_releases: int = 0
    draft_release_count: int = 0
    rolled_back_release_count: int = 0
    rollback_available: bool = False
    latest_release_created_at: datetime | None = None
    approved_at: datetime | None = None
    attention_needed: bool = False


class AppRegistryOverviewSummary(BaseModel):
    total_apps: int = 0
    apps_with_drafts: int = 0
    apps_with_rollbacks: int = 0
    apps_with_rollback_targets: int = 0
    shape_counts: dict[str, int] = Field(default_factory=dict)
    release_status_counts: dict[str, int] = Field(default_factory=dict)
    items: list[AppRegistryOverviewItem] = Field(default_factory=list)


class AppInstallResult(BaseModel):
    app_instance_id: str
    blueprint_id: str
    install_status: InstallStatus
    execution_mode: Literal["service", "pipeline"]
    status: str
    release_version: str = Field(default="0.1.0")
    app_shape: str = Field(default="generic")
    runtime_profile: AppRuntimeProfile = Field(default_factory=AppRuntimeProfile)
