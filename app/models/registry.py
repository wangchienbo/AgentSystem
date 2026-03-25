from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.app_profile import AppRuntimeProfile

RegistryStatus = Literal["draft", "registered", "deprecated", "archived"]
InstallStatus = Literal["installed", "upgraded"]


class AppRegistryEntry(BaseModel):
    blueprint_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    status: RegistryStatus = "registered"
    description: str = ""
    app_shape: str = Field(default="generic")
    runtime_profile_summary: AppRuntimeProfile = Field(default_factory=AppRuntimeProfile)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppInstallResult(BaseModel):
    app_instance_id: str
    blueprint_id: str
    install_status: InstallStatus
    execution_mode: Literal["service", "pipeline"]
    status: str
    app_shape: str = Field(default="generic")
    runtime_profile: AppRuntimeProfile = Field(default_factory=AppRuntimeProfile)
