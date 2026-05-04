from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.context_storage_paths import ContextStoragePaths, build_context_storage_paths


@dataclass
class ContextRecoveryManager:
    paths: ContextStoragePaths
    ready: bool = False
    recovering: bool = False

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = "/root/project/AgentSystem/data/context_center") -> "ContextRecoveryManager":
        return cls(paths=build_context_storage_paths(base_dir))

    def mark_recovering(self) -> None:
        self.recovering = True
        self.ready = False

    def mark_ready(self) -> None:
        self.recovering = False
        self.ready = True
