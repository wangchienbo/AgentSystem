from typing import Literal

from pydantic import BaseModel


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
