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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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


class AppInstallResult(BaseModel):
    app_instance_id: str
    blueprint_id: str
    install_status: InstallStatus
    execution_mode: Literal["service", "pipeline"]
    status: str
    release_version: str = Field(default="0.1.0")
    app_shape: str = Field(default="generic")
    runtime_profile: AppRuntimeProfile = Field(default_factory=AppRuntimeProfile)
