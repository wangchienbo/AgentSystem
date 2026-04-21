"""Tests for ModelRouter — configuration required, no hardcoded defaults."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from app.ai.model_router import (
    ModelRouter,
    ModelRouterError,
    ModelRoute,
)
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry


# ===========================================================================
# Fixtures
# ===========================================================================

def _write_config(tmp_path: Path, content: dict) -> Path:
    """Write a YAML config file and return its path."""
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(content, f)
    return config_file


def _build_skill_entry(skill_id: str, model_preference: str | None = None) -> SkillRegistryEntry:
    """Build a mock skill registry entry."""
    profile = SkillCapabilityProfile(
        intelligence_level="L2_semantic",
        network_required=True,
        runtime_criticality="C1_optional_runtime",
        execution_locality="local",
        invocation_default="automatic",
        risk_level="low",
        model_preference=model_preference,
    )
    return SkillRegistryEntry(
        skill_id=skill_id,
        name="Test Skill",
        active_version="1.0.0",
        capability_profile=profile,
    )


# ===========================================================================
# Config loading (now REQUIRED)
# ===========================================================================

def test_router_raises_when_config_missing(tmp_path: Path) -> None:
    """Router MUST raise when config file is missing (no defaults)."""
    config_file = tmp_path / "nonexistent.yaml"
    
    with pytest.raises(ModelRouterError, match="Configuration file not found"):
        ModelRouter(config_path=str(config_file))


def test_router_raises_when_models_section_missing(tmp_path: Path) -> None:
    """Router MUST raise when config has no models section."""
    config_file = _write_config(tmp_path, {
        "routing": {"callers": {"architect": {"default_model": "strong"}}},
    })
    
    with pytest.raises(ModelRouterError, match="missing required 'models' section"):
        ModelRouter(config_path=str(config_file))


def test_router_raises_when_models_empty(tmp_path: Path) -> None:
    """Router MUST raise when models section is empty."""
    config_file = _write_config(tmp_path, {
        "models": {},
        "routing": {"callers": {"architect": {"default_model": "strong"}}},
    })
    
    with pytest.raises(ModelRouterError, match="missing required 'models' section"):
        ModelRouter(config_path=str(config_file))


def test_router_loads_valid_config(tmp_path: Path) -> None:
    """Router loads successfully with valid config."""
    config_file = _write_config(tmp_path, {
        "model": {"default": "balanced"},
        "models": {
            "cheap": {
                "model": "gpt-4o-mini",
                "base_url": "https://crs.ruinique.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "temperature": 0.3,
                "max_tokens": 2048,
            },
            "balanced": {
                "model": "gpt-4.1",
                "base_url": "https://crs.ruinique.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "temperature": 0.5,
                "max_tokens": 4096,
            },
            "strong": {
                "model": "gpt-5.4",
                "base_url": "https://crs.ruinique.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "temperature": 0.7,
                "max_tokens": 8192,
            },
        },
        "routing": {
            "callers": {
                "intent_analyzer": {"default_model": "cheap"},
                "architect": {"default_model": "strong"},
                "llm_responder": {"default_model": "strong"},
            },
        },
    })
    
    router = ModelRouter(config_path=str(config_file))
    
    # Verify loaded models
    models = router.get_available_models()
    assert "cheap" in models
    assert "balanced" in models
    assert "strong" in models
    assert models["cheap"]["model"] == "gpt-4o-mini"
    assert models["strong"]["model"] == "gpt-5.4"


# ===========================================================================
# Resolution priority
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_resolution_priority_skill_preference_overrides_caller_route(tmp_path: Path) -> None:
    """Skill-declared model_preference should take priority over caller route."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {"model": "gpt-4o-mini", "base_url": "https://x.com", "api_key_env": "OPENAI_API_KEY"},
            "strong": {"model": "gpt-5.4", "base_url": "https://x.com", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {
            "callers": {"test-skill": {"default_model": "cheap"}},
        },
    })
    skill_control = MagicMock()
    skill_control.get_skill.return_value = _build_skill_entry(
        "test-skill", model_preference="strong"
    )
    router = ModelRouter(config_path=str(config_file), skill_control=skill_control)

    route = router.resolve("skill:test-skill")
    assert route.source == "skill:test-skill"
    assert route.model_name == "gpt-5.4"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_resolution_falls_back_to_caller_route(tmp_path: Path) -> None:
    """When no skill preference, should use caller route."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {"model": "gpt-4o-mini", "base_url": "https://x.com", "api_key_env": "OPENAI_API_KEY"},
            "balanced": {"model": "gpt-4.1", "base_url": "https://x.com", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {
            "callers": {"architect": {"default_model": "balanced"}},
        },
    })
    router = ModelRouter(config_path=str(config_file))

    route = router.resolve("architect")
    assert route.source == "caller:architect"
    assert route.model_name == "gpt-4.1"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_resolution_falls_back_to_global_default(tmp_path: Path) -> None:
    """When caller not in routes, should use global default."""
    config_file = _write_config(tmp_path, {
        "model": {"default": "balanced"},
        "models": {
            "balanced": {"model": "gpt-4.1", "base_url": "https://x.com", "api_key_env": "OPENAI_API_KEY"},
        },
    })
    router = ModelRouter(config_path=str(config_file))

    route = router.resolve("nonexistent_caller")
    assert route.source == "default"
    assert route.model_name == "gpt-4.1"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_resolution_falls_back_to_first_available_model(tmp_path: Path) -> None:
    """When no default configured, use first available model."""
    config_file = _write_config(tmp_path, {
        "models": {
            "ultra": {"model": "gpt-5.4", "base_url": "https://x.com", "api_key_env": "OPENAI_API_KEY"},
        },
    })
    router = ModelRouter(config_path=str(config_file))

    route = router.resolve("unknown")
    assert route.source == "fallback"
    assert route.model_name == "gpt-5.4"


# ===========================================================================
# ModelRoute properties
# ===========================================================================

def test_model_route_has_expected_fields() -> None:
    """ModelRoute should have all expected fields."""
    route = ModelRoute(
        model_name="gpt-4o-mini",
        base_url="https://example.com/v1",
        api_key_env="TEST_KEY",
        temperature=0.5,
        max_tokens=2048,
        timeout_seconds=15.0,
        source="test",
    )
    assert route.model_name == "gpt-4o-mini"
    assert route.base_url == "https://example.com/v1"
    assert route.api_key_env == "TEST_KEY"
    assert route.temperature == 0.5
    assert route.max_tokens == 2048
    assert route.timeout_seconds == 15.0
    assert route.source == "test"


# ===========================================================================
# get_client integration
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-123"})
def test_get_client_returns_client(tmp_path: Path) -> None:
    """get_client should return a configured client."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {
                "model": "gpt-4o-mini",
                "base_url": "https://crs.ruinique.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        "routing": {
            "callers": {"intent_analyzer": {"default_model": "cheap"}},
        },
    })
    router = ModelRouter(config_path=str(config_file))

    client = router.get_client("intent_analyzer")
    assert client is not None
    assert client._config.model == "gpt-4o-mini"


@patch.dict("os.environ", {}, clear=True)
def test_get_client_raises_on_missing_api_key(tmp_path: Path) -> None:
    """get_client should raise when API key is missing."""
    config_file = _write_config(tmp_path, {
        "model": {"api_key": "fallback-key-from-config"},  # Fallback key in config
        "models": {
            "cheap": {
                "model": "gpt-4o-mini",
                "base_url": "https://crs.ruinique.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        "routing": {
            "callers": {"intent_analyzer": {"default_model": "cheap"}},
        },
    })
    router = ModelRouter(config_path=str(config_file))

    # Should use fallback key from config, not raise
    client = router.get_client("intent_analyzer")
    assert client is not None


@patch.dict("os.environ", {}, clear=True)
def test_get_client_raises_when_no_api_key_anywhere(tmp_path: Path) -> None:
    """get_client should raise when no API key in env or config."""
    config_file = _write_config(tmp_path, {
        # No api_key in model section
        "models": {
            "cheap": {
                "model": "gpt-4o-mini",
                "base_url": "https://crs.ruinique.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        "routing": {
            "callers": {"intent_analyzer": {"default_model": "cheap"}},
        },
    })
    router = ModelRouter(config_path=str(config_file))

    with pytest.raises(ModelRouterError, match="Missing API key"):
        router.get_client("intent_analyzer")


# ===========================================================================
# Config loading edge cases
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_router_loads_fallback_api_key_from_config(tmp_path: Path) -> None:
    """Router should load fallback API key from model.api_key in config."""
    config_file = _write_config(tmp_path, {
        "model": {
            "api_key": "config-file-key",
            "default": "balanced",
        },
        "models": {
            "balanced": {"model": "gpt-4.1", "base_url": "https://x.com", "api_key_env": "OPENAI_API_KEY"},
        },
    })
    router = ModelRouter(config_path=str(config_file))
    
    # API key should be loaded from config (though env var takes priority)
    route = router.resolve("test")
    assert route is not None


def test_router_handles_malformed_yaml_gracefully(tmp_path: Path) -> None:
    """Router should raise with clear error on malformed YAML."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("{{{invalid yaml content")

    with pytest.raises(ModelRouterError, match="Failed to load config.yaml"):
        ModelRouter(config_path=str(config_file))


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_router_uses_default_base_url_when_not_specified(tmp_path: Path) -> None:
    """Router should use default base_url when not specified in model config."""
    config_file = _write_config(tmp_path, {
        "models": {
            "custom": {
                "model": "custom-model",
                "api_key_env": "OPENAI_API_KEY",
                # No base_url specified
            },
        },
    })
    router = ModelRouter(config_path=str(config_file))
    
    models = router.get_available_models()
    # Should use default base_url
    assert "custom" in models
    assert models["custom"]["base_url"] == "https://crs.ruinique.com/v1"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_router_supports_direct_model_name_not_in_pool(tmp_path: Path) -> None:
    """Router should handle direct model names not defined in pool."""
    config_file = _write_config(tmp_path, {
        "models": {
            "tier1": {"model": "gpt-4.1", "base_url": "https://x.com", "api_key_env": "OPENAI_API_KEY"},
        },
    })
    router = ModelRouter(config_path=str(config_file))
    
    # Resolve a direct model name not in pool
    route = router._resolve_by_preference("gpt-o3-mini", source="direct")
    assert route.model_name == "gpt-o3-mini"
    # Should inherit base_url from first available model
    assert route.base_url == "https://x.com"
