from typing import Literal

from pydantic import BaseModel, Field

from app.models.runtime_policy import RuntimePolicy
from app.models.app_profile import AppRuntimeProfile


AppStatus = Literal[
    "draft",
    "validating",
    "compiled",
    "installed",
    "running",
    "paused",
    "stopped",
    "failed",
    "upgrading",
    "archived",
]


class AppInstance(BaseModel):
    id: str
    blueprint_id: str
    owner_user_id: str
    status: AppStatus = "draft"
    installed_version: str = "0.1.0"
    data_namespace: str
    execution_mode: Literal["service", "pipeline"] = "service"
    runtime_policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    system_skills: list[str] = Field(default_factory=list)
    resolved_skills: list[str] = Field(default_factory=list)
    runtime_profile: AppRuntimeProfile = Field(default_factory=AppRuntimeProfile)
