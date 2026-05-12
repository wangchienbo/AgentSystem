from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.runtime_paths import resolve_runtime_paths


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = resolve_runtime_paths().data_dir
DEFAULT_LOGS_DIR = DEFAULT_REPO_ROOT / "logs"
DEFAULT_SCRIPTS_DIR = DEFAULT_REPO_ROOT / "scripts"
DEFAULT_CONTEXT_CENTER_DIR = DEFAULT_DATA_DIR / "context_center"
DEFAULT_CHAT_REGRESSION_DIR = DEFAULT_DATA_DIR / "chat_regression"
DEFAULT_CHAT_OBSERVATION_DIR = DEFAULT_DATA_DIR / "chat_observation"
DEFAULT_REPLAY_REGRESSION_SAMPLES_DIR = DEFAULT_DATA_DIR / "replay_regression_samples"
DEFAULT_AUDIT_LOG_DIR = DEFAULT_LOGS_DIR / "audit"


@dataclass(frozen=True)
class ContextStoragePaths:
    base_dir: Path
    detail_dir: Path
    summary_dir: Path
    buffer_dir: Path


def build_context_storage_paths(base_dir: str | Path | None = None) -> ContextStoragePaths:
    base = Path(base_dir) if base_dir is not None else resolve_runtime_paths().data_dir / "context_center"
    return ContextStoragePaths(
        base_dir=base,
        detail_dir=base / "detail",
        summary_dir=base / "summary",
        buffer_dir=base / "buffer",
    )
