"""Path Store — persistent path definitions loaded from YAML.

Paths are user-curated operation flows stored as YAML files.
App loads them at startup into memory for keyed execution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PathStep:
    """Single step in a path execution chain."""
    name: str
    skill: str
    action: str = "execute"
    inputs: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None
    timeout: float = 30.0
    max_retries: int = 1
    retry_delay: float = 5.0
    on_failure: str = "abort"  # "abort" | "skip" | "fallback"


@dataclass
class PathTemplate:
    """A path = a curated execution flow."""
    path_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    offline_capable: bool = False
    offline_fallback: str | None = None
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    steps: list[PathStep] = field(default_factory=list)


class PathStoreError(Exception):
    pass


class PathStore:
    """Loads, saves, and manages path definitions from YAML files.

    Directory layout:
        data/paths/
            maoxuan_analysis.yaml
            system_status.yaml
            ...
    """

    def __init__(self, paths_dir: str = "data/paths") -> None:
        self._paths_dir = Path(paths_dir)
        self._paths_dir.mkdir(parents=True, exist_ok=True)
        self._paths: dict[str, PathTemplate] = {}

    # -- Loading --------------------------------------------------------------

    def load_all(self) -> dict[str, PathTemplate]:
        """Load all YAML path definitions from the paths directory."""
        self._paths.clear()
        yaml_files = list(self._paths_dir.glob("*.yaml")) + list(self._paths_dir.glob("*.yml"))
        for yaml_file in yaml_files:
            try:
                path = self._load_one(yaml_file)
                self._paths[path.path_id] = path
            except Exception:
                logger.exception("Failed to load path from %s", yaml_file)
        logger.info("Loaded %d paths from %s", len(self._paths), self._paths_dir)
        return self._paths

    def _load_one(self, yaml_file: Path) -> PathTemplate:
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "path_id" not in data:
            raise PathStoreError(f"Missing path_id in {yaml_file}")

        steps = []
        for step_data in data.get("steps", []):
            steps.append(PathStep(
                name=step_data["name"],
                skill=step_data["skill"],
                action=step_data.get("action", "execute"),
                inputs=step_data.get("inputs", {}),
                condition=step_data.get("condition"),
                timeout=step_data.get("timeout", 30.0),
                max_retries=step_data.get("max_retries", 1),
                retry_delay=step_data.get("retry_delay", 5.0),
                on_failure=step_data.get("on_failure", "abort"),
            ))

        return PathTemplate(
            path_id=data["path_id"],
            name=data.get("name", data["path_id"]),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            offline_capable=data.get("offline_capable", False),
            offline_fallback=data.get("offline_fallback"),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            steps=steps,
        )

    # -- Saving ---------------------------------------------------------------

    def save(self, path: PathTemplate) -> None:
        """Save a path definition to YAML file."""
        safe_id = path.path_id.replace(".", "_")
        yaml_file = self._paths_dir / f"{safe_id}.yaml"

        data = {
            "path_id": path.path_id,
            "name": path.name,
            "description": path.description,
            "version": path.version,
            "offline_capable": path.offline_capable,
            "offline_fallback": path.offline_fallback,
            "input_schema": path.input_schema,
            "output_schema": path.output_schema,
            "steps": [
                {
                    "name": s.name,
                    "skill": s.skill,
                    "action": s.action,
                    "inputs": s.inputs,
                    "condition": s.condition,
                    "timeout": s.timeout,
                    "max_retries": s.max_retries,
                    "retry_delay": s.retry_delay,
                    "on_failure": s.on_failure,
                }
                for s in path.steps
            ],
        }

        with open(yaml_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        self._paths[path.path_id] = path
        logger.info("Saved path %s to %s", path.path_id, yaml_file)

    # -- Query ----------------------------------------------------------------

    def get(self, path_id: str) -> PathTemplate | None:
        return self._paths.get(path_id)

    def list_paths(self) -> list[PathTemplate]:
        return list(self._paths.values())

    def list_online_paths(self) -> list[PathTemplate]:
        return [p for p in self._paths.values() if not p.offline_capable]

    def list_offline_paths(self) -> list[PathTemplate]:
        return [p for p in self._paths.values() if p.offline_capable]

    def remove(self, path_id: str) -> bool:
        """Remove a path (file + memory)."""
        path = self._paths.pop(path_id, None)
        if path:
            safe_id = path_id.replace(".", "_")
            yaml_file = self._paths_dir / f"{safe_id}.yaml"
            yaml_file.unlink(missing_ok=True)
            return True
        return False
