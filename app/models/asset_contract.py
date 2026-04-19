from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AssetKind(str, Enum):
    FIXED = "fixed_asset"
    CORE_RUNTIME = "core_runtime_asset"
    MATERIALIZED = "materialized_asset"
    SESSION = "session_asset"


class AssetType(str, Enum):
    APP = "app"
    SKILL = "skill"
    SESSION = "session"
    SERVICE = "service"
    SYSTEM = "system"


class AssetState(str, Enum):
    DECLARED = "declared"
    INSTALLING = "installing"
    STARTING = "starting"
    ACTIVE = "active"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    REMOVED = "removed"
    CRASHED = "crashed"
    PAUSED = "paused"
    UNKNOWN = "unknown"


class Visibility(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    USER_SHARED = "shared"


class AssetCapability(BaseModel):
    name: str
    description: str = ""
    method: str
    input_schema_ref: str | None = None
    output_schema_ref: str | None = None
    side_effect_level: Literal["none", "read", "write", "admin"] = "read"
    requires_runtime_alive: bool = True
    permission_hint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetDescriptor(BaseModel):
    asset_id: str
    asset_type: AssetType
    asset_kind: AssetKind = AssetKind.MATERIALIZED
    version: str = "0.0.0"
    owner_type: str = "system"
    owner_id: str = "system"
    source_of_truth: str = "runtime"
    status: AssetState = AssetState.DECLARED
    capabilities: list[AssetCapability] = Field(default_factory=list)
    invoke_contract: dict[str, Any] = Field(default_factory=dict)
    health_contract: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    name: str = ""
    description: str = ""
    visibility: Visibility = Visibility.PRIVATE
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetStateTransition(BaseModel):
    from_state: AssetState
    to_state: AssetState


ALLOWED_ASSET_STATE_TRANSITIONS: set[tuple[AssetState, AssetState]] = {
    (AssetState.DECLARED, AssetState.INSTALLING),
    (AssetState.INSTALLING, AssetState.STARTING),
    (AssetState.STARTING, AssetState.ACTIVE),
    (AssetState.STARTING, AssetState.CRASHED),
    (AssetState.ACTIVE, AssetState.DEGRADED),
    (AssetState.ACTIVE, AssetState.STOPPED),
    (AssetState.ACTIVE, AssetState.CRASHED),
    (AssetState.DEGRADED, AssetState.ACTIVE),
    (AssetState.DEGRADED, AssetState.STOPPED),
    (AssetState.DEGRADED, AssetState.CRASHED),
    (AssetState.STOPPED, AssetState.STARTING),
    (AssetState.STOPPED, AssetState.REMOVED),
    (AssetState.PAUSED, AssetState.ACTIVE),
    (AssetState.ACTIVE, AssetState.PAUSED),
}


def is_valid_asset_state_transition(from_state: AssetState, to_state: AssetState) -> bool:
    return (from_state, to_state) in ALLOWED_ASSET_STATE_TRANSITIONS
