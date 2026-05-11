"""Skill Config Center — runtime configuration for all skills.

Stores model, prompt, action definitions for each skill.
Sources: local YAML, remote API (optional).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from app.runtime_paths import resolve_runtime_paths

logger = logging.getLogger(__name__)


class SkillConfigCenter:
    """Configuration registry for Skill Workers.

    Each skill entry contains:
    - model: provider, model name, temperature, max_tokens
    - actions: {action_name: {system_prompt, user_prompt, input_schema, output_format}}
    - metadata: name, description, version

    Priority: runtime set() > local YAML > defaults
    """

    def __init__(self, config_file: str | None = None) -> None:
        resolved_config_file = Path(config_file) if config_file else resolve_runtime_paths().data_dir / "skill_config" / "registry.yaml"
        self._config_file = resolved_config_file
        self._configs: dict[str, dict[str, Any]] = {}
        self._load_local()

    def _load_local(self) -> None:
        if self._config_file.exists():
            try:
                with open(self._config_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._configs = data.get("skills", {})
                logger.info("Loaded %d skill configs from %s", len(self._configs), self._config_file)
            except Exception:
                logger.exception("Failed to load skill config from %s", self._config_file)

    def get(self, skill_id: str) -> dict[str, Any] | None:
        return self._configs.get(skill_id)

    def set(self, skill_id: str, config: dict[str, Any]) -> None:
        self._configs[skill_id] = config
        self._save()

    def remove(self, skill_id: str) -> bool:
        if skill_id in self._configs:
            del self._configs[skill_id]
            self._save()
            return True
        return False

    def list_all(self) -> list[dict[str, Any]]:
        return [{"skill_id": sid, **cfg} for sid, cfg in self._configs.items()]

    def has(self, skill_id: str) -> bool:
        return skill_id in self._configs

    def _save(self) -> None:
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_file, "w", encoding="utf-8") as f:
            yaml.dump({"skills": self._configs}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
