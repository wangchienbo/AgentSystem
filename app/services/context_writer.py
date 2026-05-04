from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.context_storage_paths import ContextStoragePaths, build_context_storage_paths


@dataclass
class ContextWriter:
    paths: ContextStoragePaths

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = "/root/project/AgentSystem/data/context_center") -> "ContextWriter":
        paths = build_context_storage_paths(base_dir)
        paths.detail_dir.mkdir(parents=True, exist_ok=True)
        paths.summary_dir.mkdir(parents=True, exist_ok=True)
        paths.buffer_dir.mkdir(parents=True, exist_ok=True)
        return cls(paths=paths)
