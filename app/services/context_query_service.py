from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.context_storage_paths import ContextStoragePaths, build_context_storage_paths


@dataclass
class ContextQueryService:
    paths: ContextStoragePaths

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = "/root/project/AgentSystem/data/context_center") -> "ContextQueryService":
        return cls(paths=build_context_storage_paths(base_dir))
