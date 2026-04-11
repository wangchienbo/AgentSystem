from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetaAppBootstrapRequest(BaseModel):
    """Request for bootstrapping an app-scoped control structure inside AgentSystem."""

    app_name: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    app_kind: str = Field(default="service")
    context: dict[str, Any] = Field(default_factory=dict)


class MetaAppScopeRecord(BaseModel):
    scope_id: str
    purpose: str
    category: str = "app-module"
    owned_paths: list[str] = Field(default_factory=list)


class MetaAppBootstrapResult(BaseModel):
    app_name: str
    anchor_name: str
    project_map_name: str
    module_records: list[MetaAppScopeRecord] = Field(default_factory=list)
    subordinate_registry_name: str
    notes: list[str] = Field(default_factory=list)
