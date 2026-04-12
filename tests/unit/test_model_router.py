"""Tests for ModelRouter — unified model routing."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.model_router import (
    DEFAULT_CALLER_ROUTES,
    DEFAULT_MODEL_POOL,
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
    import yaml
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
# Default configuration
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_model_router_uses_defaults_when_no_config(tmp_path: Path) -> None:
    """Router falls back to defaults when config file doesn't exist."""
    config_file = tmp_path / "nonexistent.yaml"
    router = ModelRouter(config_path=str(config_file))

    # Should still resolve with defaults
    route = router.resolve("architect")
    assert route.source == "caller:architect"
    assert route.model_name == DEFAULT_MODEL_POOL["strong"]["model"]

    route = router.resolve("unknown_caller")
    assert route.source == "default"


def test_default_model_pool_has_three_tiers() -> None:
    """Default pool should have cheap, balanced, strong tiers."""
    assert "cheap" in DEFAULT_MODEL_POOL
    assert "balanced" in DEFAULT_MODEL_POOL
    assert "strong" in DEFAULT_MODEL_POOL
    assert DEFAULT_MODEL_POOL["cheap"]["model"] == "gpt-4o-mini"
    assert DEFAULT_MODEL_POOL["strong"]["model"] == "gpt-5.4"


def test_default_caller_routes_exist() -> None:
    """Default caller routes should cover key components."""
    assert "intent_analyzer" in DEFAULT_CALLER_ROUTES
    assert "architect" in DEFAULT_CALLER_ROUTES
    assert DEFAULT_CALLER_ROUTES["intent_analyzer"]["default_model"] == "cheap"
    assert DEFAULT_CALLER_ROUTES["architect"]["default_model"] == "strong"


# ===========================================================================
# Config loading
# ===========================================================================

def test_model_router_loads_custom_model_pool(tmp_path: Path) -> None:
    """Router should load custom model pool from config."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {
                "model": "gpt-4o-mini",
                "base_url": "https://custom.example.com/v1",
                "api_key_env": "CUSTOM_API_KEY",
                "temperature": 0.2,
                "max_tokens": 1024,
            },
            "ultra": {
                "model": "gpt-5.4",
                "base_url": "https://custom.example.com/v1",
                "api_key_env": "CUSTOM_API_KEY",
            },
        },
    })
    router = ModelRouter(config_path=str(config_file))

    models = router.get_available_models()
    assert "cheap" in models
    assert models["cheap"]["model"] == "gpt-4o-mini"
    assert models["cheap"]["base_url"] == "https://custom.example.com/v1"
    assert models["cheap"]["temperature"] == 0.2
    assert "ultra" in models


def test_model_router_loads_caller_routes(tmp_path: Path) -> None:
    """Router should load custom caller routes from config."""
    config_file = _write_config(tmp_path, {
        "routing": {
            "callers": {
                "intent_analyzer": {"default_model": "ultra"},
                "custom_service": {"default_model": "balanced"},
            },
        },
    })
    router = ModelRouter(config_path=str(config_file))

    # Custom route should override default
    route = router.resolve("intent_analyzer")
    assert route.source == "caller:intent_analyzer"


def test_model_router_loads_default_model(tmp_path: Path) -> None:
    """Router should load default model setting from config."""
    config_file = _write_config(tmp_path, {
        "model": {"default": "balanced"},
    })
    router = ModelRouter(config_path=str(config_file))

    route = router.resolve("unknown_caller_not_in_routes")
    assert route.source == "default"


def test_model_router_handles_malformed_config(tmp_path: Path) -> None:
    """Router should gracefully handle malformed config files."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("{{{invalid yaml content")

    # Should not raise, fall back to defaults
    router = ModelRouter(config_path=str(config_file))
    assert router.get_available_models() is not None


def test_model_router_handles_empty_config(tmp_path: Path) -> None:
    """Router should handle empty config files."""
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("")

    router = ModelRouter(config_path=str(config_file))
    assert len(router.get_available_models()) > 0


# ===========================================================================
# Resolution priority
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_resolution_priority_skill_preference_overrides_caller_route(tmp_path: Path) -> None:
    """Skill-declared model_preference should take priority over caller route."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {"model": "gpt-4o-mini"},
            "strong": {"model": "gpt-5.4"},
        },
    })
    skill_control = MagicMock()
    skill_control.get_skill.return_value = _build_skill_entry(
        "test-skill", model_preference="strong"
    )
    router = ModelRouter(config_path=str(config_file), skill_control=skill_control)

    route = router.resolve("skill:test-skill")
    assert route.source == "skill:test-skill"


def test_resolution_falls_back_to_caller_route(tmp_path: Path) -> None:
    """When no skill preference, should use caller route."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {"model": "gpt-4o-mini"},
            "balanced": {"model": "gpt-4.1"},
        },
    })
    router = ModelRouter(config_path=str(config_file))

    route = router.resolve("architect")
    assert route.source == "caller:architect"


def test_resolution_falls_back_to_global_default(tmp_path: Path) -> None:
    """When caller not in routes, should use global default."""
    config_file = _write_config(tmp_path, {
        "model": {"default": "balanced"},
        "models": {
            "balanced": {"model": "gpt-4.1"},
        },
    })
    router = ModelRouter(config_path=str(config_file))

    route = router.resolve("nonexistent_caller")
    assert route.source == "default"


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
            "callers": {
                "intent_analyzer": {"default_model": "cheap"},
            },
        },
    })
    router = ModelRouter(config_path=str(config_file))

    client = router.get_client("intent_analyzer")
    assert client is not None


@patch.dict("os.environ", {}, clear=True)
def test_get_client_raises_on_missing_api_key(tmp_path: Path) -> None:
    """get_client should raise when API key is missing."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {
                "model": "gpt-4o-mini",
                "base_url": "https://crs.ruinique.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        "routing": {
            "callers": {
                "intent_analyzer": {"default_model": "cheap"},
            },
        },
    })
    router = ModelRouter(config_path=str(config_file))

    with pytest.raises(ModelRouterError, match="Missing API key"):
        router.get_client("intent_analyzer")


# ===========================================================================
# Skill control integration
# ===========================================================================

@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_skill_model_preference_read_from_registry(tmp_path: Path) -> None:
    """Router should read model_preference from skill registry entry."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {"model": "gpt-4o-mini"},
            "strong": {"model": "gpt-5.4"},
        },
    })
    skill_control = MagicMock()
    skill_control.get_skill.return_value = _build_skill_entry(
        "my-skill", model_preference="strong"
    )
    router = ModelRouter(config_path=str(config_file), skill_control=skill_control)

    route = router.resolve("skill:my-skill")
    assert route.source == "skill:my-skill"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_skill_without_preference_falls_back(tmp_path: Path) -> None:
    """Skill without model_preference should fall back to caller route."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {"model": "gpt-4o-mini"},
            "balanced": {"model": "gpt-4.1"},
        },
    })
    skill_control = MagicMock()
    skill_control.get_skill.return_value = _build_skill_entry(
        "my-skill", model_preference=None
    )
    router = ModelRouter(config_path=str(config_file), skill_control=skill_control)

    # Falls back to default since "skill:my-skill" isn't in caller routes
    route = router.resolve("skill:my-skill")
    assert route is not None


def test_skill_control_error_falls_back(tmp_path: Path) -> None:
    """Router should handle skill registry errors gracefully."""
    config_file = _write_config(tmp_path, {
        "models": {
            "cheap": {"model": "gpt-4o-mini"},
        },
    })
    skill_control = MagicMock()
    skill_control.get_skill.side_effect = RuntimeError("registry down")
    router = ModelRouter(config_path=str(config_file), skill_control=skill_control)

    # Should fall back, not raise
    route = router.resolve("skill:my-skill")
    assert route is not None


def test_no_skill_control_uses_defaults(tmp_path: Path) -> None:
    """Router should work without skill_control."""
    router = ModelRouter()
    route = router.resolve("unknown")
    assert route is not None
