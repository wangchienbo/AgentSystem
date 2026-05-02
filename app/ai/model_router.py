"""Unified Model Router — all LLM calls go through here.

Routing priority:
1. Skill-declared model_preference (direct model name or cost tier alias)
2. Caller-type routing table (configurable via YAML)
3. Global default model

Usage:
    router = ModelRouter()
    client = router.get_client("skill:maoxuan")          # uses skill's model_preference
    client = router.get_client("architect", "complex")   # uses caller routing

Configuration REQUIRED: /root/.config/agentsystem/config.yaml must exist
with model pool and routing definitions.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.services.model_client import OpenAIResponsesClient, ModelClientError


DEFAULT_CONFIG_PATH = Path("/root/.config/agentsystem/config.yaml")
DEFAULT_PREFERENCE_ALIASES = {
    "cheap": "gpt-4o-mini",
    "balanced": "gpt-4.1",
    "strong": "gpt-5.4",
}


@dataclass
class ModelRoute:
    """Resolved model route."""
    model_name: str
    base_url: str
    api_key_env: str
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout_seconds: float = 30.0
    source: str = ""  # "skill", "caller", "default"


class ModelRouterError(ValueError):
    pass


class ModelRouter:
    """Unified model router for all LLM calls in AgentSystem.

    Configuration priority (high → low):
    1. App-skill binding override (from ConfigCenterService)
    2. Skill template default (from ConfigCenterService)
    3. Skill-declared model_preference (from SkillRegistryEntry)
    4. Caller-type routing table
    5. Global default

    NOTE: No hardcoded defaults. Config MUST be loaded from config.yaml.
    """

    def __init__(
        self,
        config_path: str | None = None,
        skill_control: Any = None,
        config_center: Any = None,
    ) -> None:
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._skill_control = skill_control
        self._config_center = config_center  # ConfigCenterService
        self._model_pool: dict[str, dict[str, Any]] = {}  # NO defaults - must load from config
        self._caller_routes: dict[str, dict[str, str]] = {}  # NO defaults - must load from config
        self._default_model: str | None = None  # NO default - must load from config
        self._fallback_api_key: str | None = None  # From config file model.api_key
        self._load_config()

    def _load_config(self) -> None:
        """Load model pool and routing from config.yaml.
        
        Raises ModelRouterError if config is missing or invalid.
        """
        if not self._config_path.exists():
            raise ModelRouterError(
                f"Configuration file not found: {self._config_path}\n"
                f"Please create config.yaml with models and routing definitions."
            )

        try:
            raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            raise ModelRouterError(f"Failed to load config.yaml: {e}")

        # Load fallback API key from model.api_key (top-level config)
        model_section = raw.get("model")
        if isinstance(model_section, dict):
            self._fallback_api_key = model_section.get("api_key")
            default = model_section.get("default")
            if default:
                self._default_model = default

        # Load model pool (REQUIRED)
        models_section = raw.get("models")
        if not isinstance(models_section, dict) or not models_section:
            raise ModelRouterError(
                f"Config missing required 'models' section with model definitions."
            )
        
        for alias, cfg in models_section.items():
            if not isinstance(cfg, dict):
                continue
            model_name = cfg.get("model", alias)
            self._model_pool[alias] = {
                "model": model_name,
                "base_url": cfg.get("base_url", model_section.get("base_url", "https://crs.ruinique.com/v1") if isinstance(model_section, dict) else "https://crs.ruinique.com/v1"),
                "api_key_env": cfg.get("api_key_env", model_section.get("api_key_env", "OPENAI_API_KEY") if isinstance(model_section, dict) else "OPENAI_API_KEY"),
                "temperature": float(cfg.get("temperature", 0.7)),
                "max_tokens": int(cfg.get("max_tokens", 4096)),
                "timeout_seconds": float(cfg.get("timeout_seconds", model_section.get("timeout_seconds", 30.0) if isinstance(model_section, dict) else 30.0)),
            }

        # Load caller routes (REQUIRED)
        routing_section = raw.get("routing")
        if isinstance(routing_section, dict):
            callers = routing_section.get("callers")
            if isinstance(callers, dict):
                self._caller_routes.update(callers)

        # Validate that we have at least some models
        if not self._model_pool:
            raise ModelRouterError("No valid model definitions found in config.yaml")

    def resolve(self, caller: str, complexity: str = "moderate") -> ModelRoute:
        """Resolve which model to use for a given caller.

        Priority:
        1. App-skill binding override (from ConfigCenterService)
        2. Skill template default (from ConfigCenterService)
        3. Skill-declared model_preference (from SkillRegistryEntry)
        4. Caller-type routing table
        5. Global default
        """
        # Parse caller format: "asset:{asset_id}:skill:{skill_id}" or "skill:{skill_id}" or "app:{app_id}"
        asset_id = None
        app_id = None
        skill_id = None

        if caller.startswith("asset:"):
            # Format: asset:{asset_id}:skill:{skill_id} or asset:{asset_id}:app:{app_id}
            parts = caller.split(":")
            if len(parts) >= 4:
                asset_id = parts[1]
                if parts[2] == "skill" and len(parts) >= 4:
                    skill_id = parts[3]
                elif parts[2] == "app" and len(parts) >= 4:
                    app_id = parts[3]
        elif ":app:" in caller:
            # Legacy format: skill:{skill_id}:app:{app_id}
            parts = caller.split(":")
            skill_id = parts[1] if len(parts) > 1 else None
            app_id = parts[3] if len(parts) > 3 else None
        elif caller.startswith("skill:"):
            skill_id = caller.split(":", 1)[1]
        elif caller.startswith("app:"):
            app_id = caller.split(":", 1)[1]

        # 0. ConfigCenter: app-skill binding + skill template defaults
        if self._config_center:
            resolved = self._config_center.resolve_model_preference(app_id, skill_id)
            if resolved:
                return self._resolve_by_preference(resolved, source=f"config_center:{caller}")

        # 1. Skill-declared preference
        if caller.startswith("skill:"):
            skill_id = caller.split(":", 1)[1]
            pref = self._get_skill_model_preference(skill_id)
            if pref:
                return self._resolve_by_preference(pref, source=f"skill:{skill_id}")

        # 2. Caller routing table
        caller_cfg = self._caller_routes.get(caller)
        if isinstance(caller_cfg, dict):
            model_key = caller_cfg.get("default_model")
            if model_key:
                return self._resolve_by_preference(model_key, source=f"caller:{caller}")

        # 3. Global default
        if self._default_model:
            return self._resolve_by_preference(self._default_model, source="default")
        
        # 4. Fallback: use any available model
        if self._model_pool:
            first = next(iter(self._model_pool.keys()))
            return self._resolve_by_preference(first, source="fallback")
        
        raise ModelRouterError("No model available and no default configured")

    def get_client(self, caller: str, complexity: str = "moderate") -> OpenAIResponsesClient:
        """Resolve model and create a client in one step."""
        route = self.resolve(caller, complexity)
        api_key = self._resolve_api_key(route)
        return OpenAIResponsesClient(config=self._make_model_config(route), api_key=api_key)

    def get_available_models(self) -> dict[str, dict[str, Any]]:
        """Return all configured models."""
        return dict(self._model_pool)

    def _get_skill_model_preference(self, skill_id: str) -> str | None:
        """Read model_preference from skill registry."""
        if not self._skill_control:
            return None
        try:
            entry = self._skill_control.get_skill(skill_id)
            pref = getattr(entry.capability_profile, "model_preference", None)
            return pref if pref else None
        except Exception:
            return None

    def _resolve_by_preference(self, preference: str, source: str = "") -> ModelRoute:
        """Resolve a preference string (model name or cost tier alias) to a ModelRoute."""
        resolved_preference = DEFAULT_PREFERENCE_ALIASES.get(preference, preference)

        # Direct model name/alias match in pool.
        if resolved_preference in self._model_pool:
            cfg = self._model_pool[resolved_preference]
            return ModelRoute(
                model_name=cfg["model"],
                base_url=cfg["base_url"],
                api_key_env=cfg["api_key_env"],
                temperature=cfg["temperature"],
                max_tokens=cfg["max_tokens"],
                timeout_seconds=cfg.get("timeout_seconds", 30.0),
                source=source,
            )

        # Match by declared model name in the pool.
        for cfg in self._model_pool.values():
            if cfg.get("model") == resolved_preference:
                return ModelRoute(
                    model_name=cfg["model"],
                    base_url=cfg["base_url"],
                    api_key_env=cfg["api_key_env"],
                    temperature=cfg["temperature"],
                    max_tokens=cfg["max_tokens"],
                    timeout_seconds=cfg.get("timeout_seconds", 30.0),
                    source=source,
                )

        # Check if preference is a direct model name not in pool
        # (use first available base_url as fallback)
        if self._model_pool:
            first = next(iter(self._model_pool.values()))
            return ModelRoute(
                model_name=resolved_preference,
                base_url=first.get("base_url", "https://crs.ruinique.com/v1"),
                api_key_env=first.get("api_key_env", "OPENAI_API_KEY"),
                temperature=0.7,
                max_tokens=4096,
                source=source,
            )
        
        raise ModelRouterError(f"No model configuration available to resolve preference: {preference}")

    def _resolve_api_key(self, route: ModelRoute) -> str:
        """Resolve API key from environment or config file."""
        # Priority 1: environment variable
        api_key = os.getenv(route.api_key_env)
        if api_key:
            return api_key
        # Priority 2: config file fallback (model.api_key)
        if self._fallback_api_key:
            return self._fallback_api_key
        raise ModelRouterError(f"Missing API key in env var: {route.api_key_env}")

    def _make_model_config(self, route: ModelRoute) -> Any:
        """Create a ModelConfig-compatible object from route."""
        from app.models.model_config import ModelConfig
        return ModelConfig(
            base_url=route.base_url,
            model=route.model_name,
            api_key_env=route.api_key_env,
            timeout_seconds=route.timeout_seconds,
        )
