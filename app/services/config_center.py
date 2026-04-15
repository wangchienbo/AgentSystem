"""Configuration Center — system-level app for managing skill and app model configurations.

Provides centralized management for:
1. Skill template defaults (skill_id → model_preference)
2. App-skill binding overrides (app_id + skill_id → model_preference)

Configuration priority (high → low):
1. App-skill binding override
2. Skill template default
3. Caller routing table
4. Global default
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============================================================
# Data models
# ============================================================

@dataclass
class SkillTemplateConfig:
    """Default configuration for a skill template."""
    skill_id: str
    model_preference: str | None = None  # "cheap" / "balanced" / "strong"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppSkillBinding:
    """App-level override for a skill's configuration."""
    app_id: str
    skill_id: str
    model_preference: str | None = None  # override template default
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Config Center Service
# ============================================================

class ConfigCenterError(Exception):
    pass


class ConfigCenterService:
    """System-level configuration center for skill and app model preferences.

    Stores:
    - _skill_templates: skill_id → SkillTemplateConfig
    - _app_bindings: (app_id, skill_id) → AppSkillBinding

    Persists to: data/config_center.json
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else Path("data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._skill_templates: dict[str, SkillTemplateConfig] = {}
        self._app_bindings: dict[tuple[str, str], AppSkillBinding] = {}
        self._load()

    # ---- Skill template configs ----

    def set_skill_config(
        self,
        skill_id: str,
        model_preference: str | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SkillTemplateConfig:
        """Set or update a skill template's default configuration."""
        config = SkillTemplateConfig(
            skill_id=skill_id,
            model_preference=model_preference,
            description=description,
            metadata=metadata or {},
        )
        self._skill_templates[skill_id] = config
        self._save()
        return config

    def get_skill_config(self, skill_id: str) -> SkillTemplateConfig | None:
        """Get a skill template's configuration."""
        return self._skill_templates.get(skill_id)

    def list_skill_configs(self) -> list[SkillTemplateConfig]:
        """List all skill template configurations."""
        return list(self._skill_templates.values())

    def delete_skill_config(self, skill_id: str) -> bool:
        """Delete a skill template configuration."""
        if skill_id in self._skill_templates:
            del self._skill_templates[skill_id]
            self._save()
            return True
        return False

    # ---- App-skill binding overrides ----

    def set_app_skill_binding(
        self,
        app_id: str,
        skill_id: str,
        model_preference: str | None = None,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> AppSkillBinding:
        """Set or update an app's binding configuration for a skill."""
        binding = AppSkillBinding(
            app_id=app_id,
            skill_id=skill_id,
            model_preference=model_preference,
            enabled=enabled,
            metadata=metadata or {},
        )
        self._app_bindings[(app_id, skill_id)] = binding
        self._save()
        return binding

    def get_app_skill_binding(self, app_id: str, skill_id: str) -> AppSkillBinding | None:
        """Get an app's binding configuration for a skill."""
        return self._app_bindings.get((app_id, skill_id))

    def get_app_bindings(self, app_id: str) -> list[AppSkillBinding]:
        """List all skill bindings for an app."""
        return [
            b for (aid, _), b in self._app_bindings.items()
            if aid == app_id
        ]

    def delete_app_skill_binding(self, app_id: str, skill_id: str) -> bool:
        """Delete an app-skill binding."""
        key = (app_id, skill_id)
        if key in self._app_bindings:
            del self._app_bindings[key]
            self._save()
            return True
        return False

    # ---- Resolution (core API) ----

    def resolve_model_preference(
        self,
        app_id: str | None = None,
        skill_id: str | None = None,
    ) -> str | None:
        """Resolve the effective model_preference using priority chain.

        Priority:
        1. App-skill binding override
        2. Skill template default
        3. None (caller should fall back to routing table / global default)
        """
        # 1. App-level override (highest priority)
        if app_id and skill_id:
            binding = self.get_app_skill_binding(app_id, skill_id)
            if binding and binding.model_preference and binding.enabled:
                return binding.model_preference

        # 2. Skill template default
        if skill_id:
            config = self.get_skill_config(skill_id)
            if config and config.model_preference:
                return config.model_preference

        # 3. Fall back to caller routing table (handled by ModelRouter)
        return None

    # ---- Batch operations for App creation/startup ----

    def resolve_all_app_skills(self, app_id: str, skill_ids: list[str]) -> dict[str, str | None]:
        """Resolve model_preference for all skills bound to an app.

        Returns {skill_id: model_preference_or_None, ...}
        """
        result = {}
        for sid in skill_ids:
            result[sid] = self.resolve_model_preference(app_id, sid)
        return result

    # Phase II.1: Per-app skill instance isolation
    def materialize_app_skill_instances(
        self,
        app_id: str,
        skill_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Materialize per-app skill instance configs from template + binding resolution.

        Returns {skill_id: {"model_preference": ..., "metadata": ..., "enabled": ...}}
        Each app instance gets its own isolated snapshot so shared skill templates
        don't leak runtime context, state, or per-app overrides between apps.
        """
        result = {}
        for sid in skill_ids:
            model_pref = self.resolve_model_preference(app_id, sid)
            template_config = self.get_skill_config(sid)
            binding = self.get_app_skill_binding(app_id, sid)
            metadata: dict[str, Any] = {}
            if template_config:
                metadata.update(template_config.metadata)
            if binding:
                metadata.update(binding.metadata)
            result[sid] = {
                "model_preference": model_pref,
                "metadata": metadata,
                "enabled": binding.enabled if binding else True,
            }
        return result

    def apply_app_skill_bindings(
        self,
        app_id: str,
        skill_configs: list[dict[str, str | None]],
    ) -> list[AppSkillBinding]:
        """Batch apply app-skill bindings from App creation.

        Each item: {"skill_id": "...", "model_preference": "..."}
        """
        bindings = []
        for item in skill_configs:
            sid = item.get("skill_id")
            mp = item.get("model_preference")
            if sid:
                binding = self.set_app_skill_binding(app_id, sid, mp)
                bindings.append(binding)
        self._save()
        return bindings

    # ---- Persistence ----

    def _save(self) -> None:
        path = self._data_dir / "config_center.json"
        data = {
            "skill_templates": {
                sid: {
                    "skill_id": c.skill_id,
                    "model_preference": c.model_preference,
                    "description": c.description,
                    "metadata": c.metadata,
                }
                for sid, c in self._skill_templates.items()
            },
            "app_bindings": {
                f"{aid}:{sid}": {
                    "app_id": b.app_id,
                    "skill_id": b.skill_id,
                    "model_preference": b.model_preference,
                    "enabled": b.enabled,
                    "metadata": b.metadata,
                }
                for (aid, sid), b in self._app_bindings.items()
            },
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> None:
        path = self._data_dir / "config_center.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return

        for sid, raw in data.get("skill_templates", {}).items():
            self._skill_templates[sid] = SkillTemplateConfig(
                skill_id=raw.get("skill_id", sid),
                model_preference=raw.get("model_preference"),
                description=raw.get("description", ""),
                metadata=raw.get("metadata", {}),
            )

        for key, raw in data.get("app_bindings", {}).items():
            aid = raw.get("app_id", "")
            sid = raw.get("skill_id", "")
            self._app_bindings[(aid, sid)] = AppSkillBinding(
                app_id=aid,
                skill_id=sid,
                model_preference=raw.get("model_preference"),
                enabled=raw.get("enabled", True),
                metadata=raw.get("metadata", {}),
            )
