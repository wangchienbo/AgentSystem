from __future__ import annotations

from pydantic import BaseModel, Field


class AppRuntimeProfile(BaseModel):
    runtime_intelligence_level: str = Field(default="L0_deterministic")
    runtime_network_requirement: str = Field(default="N0_none")
    offline_capable: bool = True
    direct_start_supported: bool = True
    invocation_posture: str = Field(default="automatic")
    runtime_skills: list[str] = Field(default_factory=list)
