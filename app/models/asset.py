"""Asset data model for the dynamic asset registry.

Only *running* instances count as assets — static blueprints are excluded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AssetType(str, Enum):
    APP = "app"
    SKILL = "skill"


class Visibility(str, Enum):
    """Who can see this asset beyond its owner."""

    PRIVATE = "private"       # only owner
    PUBLIC = "public"         # everyone (system + all users)
    USER_SHARED = "shared"    # specific users (stored in shared_with)


@dataclass
class AssetFunction:
    """One callable function provided by an asset."""

    key: str                           # unique key within the asset
    name: str                          # human-readable name
    description: str                   # short description for prompt overview
    input_schema: dict[str, Any] = field(default_factory=dict)   # detailed input schema
    output_schema: dict[str, Any] = field(default_factory=dict)  # detailed output schema
    notes: str = ""                    # usage notes / caveats


@dataclass
class Asset:
    """A running App or Skill instance registered in the asset registry."""

    asset_id: str                      # e.g. "app.novel", "skill.generic_writer"
    asset_type: AssetType
    owner_id: str                      # "user.alice" / "app.novel" / "system"
    name: str
    description: str
    visibility: Visibility = Visibility.PRIVATE
    functions: list[AssetFunction] = field(default_factory=list)
    shared_with: list[str] = field(default_factory=list)   # user_ids when visibility=shared
    metadata: dict[str, Any] = field(default_factory=dict)   # extra: status, bind_worker_id, etc.
    is_running: bool = True            # only True assets are in the registry

    # -- helpers ----------------------------------------------------------
    def add_function(self, fn: AssetFunction) -> None:
        self.functions.append(fn)

    def get_function(self, key: str) -> AssetFunction | None:
        for f in self.functions:
            if f.key == key:
                return f
        return None

    def overview(self) -> str:
        """Short overview line for prompt injection."""
        fn_names = ", ".join(f.name for f in self.functions)
        return f"- {self.asset_id}: [{fn_names}]"
