from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContextStoragePaths:
    base_dir: Path
    detail_dir: Path
    summary_dir: Path
    buffer_dir: Path


def build_context_storage_paths(base_dir: str | Path = "/root/project/AgentSystem/data/context_center") -> ContextStoragePaths:
    base = Path(base_dir)
    return ContextStoragePaths(
        base_dir=base,
        detail_dir=base / "detail",
        summary_dir=base / "summary",
        buffer_dir=base / "buffer",
    )
