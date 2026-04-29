"""Tests for App Designer components — intent_analyzer, architect, orchestrator."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.app_design import (
    AppCreationResult,
    AppDesignResult,
    AppIntentResult,
    DesignConfirmation,
    SubordinateSkillDesign,
)
from app.services.app_designer.intent_analyzer import (
    AppIntentAnalyzer,
    AppIntentAnalyzerError,
)
from app.services.app_designer.architect import (
    AppArchitect,
    AppArchitectError,
)
from app.services.app_designer.orchestrator import (
    AppDesignOrchestrator,
    AppDesignOrchestratorError,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _build_mock_client(response_text: str):
    """Build a mock model client that returns the given response."""
    mock = MagicMock()
    mock.generate_response.return_value = (response_text, {"total_tokens": 50})
    return mock


def _make_design(**overrides) -> AppDesignResult:
    """Helper to create a valid AppDesignResult with minimal required fields."""
    return AppDesignResult(
        app_name=overrides.get("app_name", "Test App"),
        app_slug=overrides.get("app_slug", "test-app"),
        control_skill_name=overrides.get("control_skill_name", "Test Control"),
        control_skill_description=overrides.get("control_skill_description", "Controls test"),
        **{k: v for k, v in overrides.items() if k not in (
            "app_name", "app_slug", "control_skill_name", "control_skill_description"
        )},
    )


def _make_intent(**overrides) -> AppIntentResult:
    return AppIntentResult(
        app_name=overrides.get("app_name", ""),
        goal=overrides.get("goal", ""),
        kind=overrides.get("kind", "service"),
        complexity=overrides.get("complexity", "moderate"),
        constraints=overrides.get("constraints", []),
        needs_clarification=overrides.get("needs_clarification", False),
        clarification_questions=overrides.get("clarification_questions", []),
        confidence=overrides.get("confidence", 0.5),
    )


# ===========================================================================
# AppIntentAnalyzer tests
# ===========================================================================

def test_analyze_parses_valid_json(tmp_path) -> None:
    """Analyzer should parse valid JSON response."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "cheap": {"model": "gpt-4o-mini", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {"callers": {"intent_analyzer": {"default_model": "cheap"}}},
    }))
    router = ModelRouter(config_path=str(config_file))

    response = json.dumps({
        "app_name": "Monitoring App",
        "goal": "Monitor server health",
        "kind": "monitoring",
        "complexity": "moderate",
        "constraints": [],
        "needs_clarification": False,
        "clarification_questions": [],
        "confidence": 0.9,
    })
    mock_client = _build_mock_client(response)

    with patch.object(router, "get_client", return_value=mock_client):
        analyzer = AppIntentAnalyzer(router)
        result = analyzer.analyze("我想做一个监控 App")

    assert result.app_name == "Monitoring App"
    assert result.goal == "Monitor server health"
    assert result.kind == "monitoring"
    assert result.confidence == 0.9
    assert result.needs_clarification is False


def test_analyze_parses_clarification_needed(tmp_path) -> None:
    """Analyzer should detect when clarification is needed."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "cheap": {"model": "gpt-4o-mini", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {"callers": {"intent_analyzer": {"default_model": "cheap"}}},
    }))
    router = ModelRouter(config_path=str(config_file))

    response = json.dumps({
        "app_name": "",
        "goal": "",
        "kind": "service",
        "complexity": "moderate",
        "constraints": [],
        "needs_clarification": True,
        "clarification_questions": ["你想要监控什么？", "有什么特殊需求？"],
        "confidence": 0.2,
    })
    mock_client = _build_mock_client(response)

    with patch.object(router, "get_client", return_value=mock_client):
        analyzer = AppIntentAnalyzer(router)
        result = analyzer.analyze("做一个 App")

    assert result.needs_clarification is True
    assert len(result.clarification_questions) == 2
    assert result.confidence == 0.2


def test_analyze_extracts_json_from_code_block(tmp_path) -> None:
    """Analyzer should extract JSON from markdown code blocks."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "cheap": {"model": "gpt-4o-mini", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {"callers": {"intent_analyzer": {"default_model": "cheap"}}},
    }))
    router = ModelRouter(config_path=str(config_file))

    response = '```json\n{"app_name": "Test", "goal": "test", "kind": "service", "complexity": "simple", "constraints": [], "needs_clarification": false, "clarification_questions": [], "confidence": 0.8}\n```'
    mock_client = _build_mock_client(response)

    with patch.object(router, "get_client", return_value=mock_client):
        analyzer = AppIntentAnalyzer(router)
        result = analyzer.analyze("test")

    assert result.app_name == "Test"


def test_analyze_fallback_on_error(tmp_path) -> None:
    """Analyzer should fallback gracefully on LLM errors."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "cheap": {"model": "gpt-4o-mini", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {"callers": {"intent_analyzer": {"default_model": "cheap"}}},
    }))
    router = ModelRouter(config_path=str(config_file))

    mock_client = MagicMock()
    mock_client.generate_response.side_effect = RuntimeError("API down")

    with patch.object(router, "get_client", return_value=mock_client):
        analyzer = AppIntentAnalyzer(router)
        result = analyzer.analyze("做一个监控 App")

    assert result.needs_clarification is True
    assert len(result.clarification_questions) > 0


def test_analyze_includes_context(tmp_path) -> None:
    """Analyzer should include context in the user message."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "cheap": {"model": "gpt-4o-mini", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {"callers": {"intent_analyzer": {"default_model": "cheap"}}},
    }))
    router = ModelRouter(config_path=str(config_file))

    response = json.dumps({
        "app_name": "Context App", "goal": "test", "kind": "service",
        "complexity": "simple", "constraints": [], "needs_clarification": False,
        "clarification_questions": [], "confidence": 0.5,
    })
    mock_client = _build_mock_client(response)

    with patch.object(router, "get_client", return_value=mock_client):
        analyzer = AppIntentAnalyzer(router)
        result = analyzer.analyze("test", context={"existing_apps": ["app1"]})

    assert result.app_name == "Context App"


# ===========================================================================
# AppArchitect tests
# ===========================================================================

def _make_architect_with_mock(router, response_text: str, skill_registry=None) -> AppArchitect:
    """Create architect with mocked client."""
    mock_client = _build_mock_client(response_text)
    patcher = patch.object(router, "get_client", return_value=mock_client)
    patcher.start()
    architect = AppArchitect(router, skill_registry=skill_registry)
    return architect, patcher


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_architect_parses_valid_design(tmp_path) -> None:
    """Architect should parse valid design response."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "strong": {"model": "gpt-5.4", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {"callers": {"architect": {"default_model": "strong"}}},
    }))
    router = ModelRouter(config_path=str(config_file))

    response = json.dumps({
        "app_name": "Monitor App",
        "app_slug": "monitor-app",
        "control_skill_name": "Monitor Control",
        "control_skill_description": "Controls the monitor app",
        "subordinate_skills": [
            {
                "suggested_name": "cpu-collector",
                "scope": "CPU metrics",
                "responsibility": "Collect CPU data",
                "priority": "high",
                "reuse_existing": None,
            },
        ],
        "reused_skills": ["existing-skill"],
        "new_skills": ["cpu-collector"],
        "decomposition_plan": ["step 1", "step 2"],
        "governance_notes": ["note 1"],
        "design_notes": "Simple design",
    })

    intent = _make_intent(app_name="Monitor", goal="Monitor stuff")
    architect, patcher = _make_architect_with_mock(router, response)
    try:
        result = architect.design(intent)
    finally:
        patcher.stop()

    assert result.app_name == "Monitor App"
    assert result.app_slug == "monitor-app"
    assert len(result.subordinate_skills) == 1
    assert result.subordinate_skills[0].suggested_name == "cpu-collector"
    assert len(result.reused_skills) == 1
    assert len(result.decomposition_plan) == 2


def test_architect_handles_empty_skill_registry(tmp_path) -> None:
    """Architect should work without a skill registry."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "strong": {"model": "gpt-5.4", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {"callers": {"architect": {"default_model": "strong"}}},
    }))
    router = ModelRouter(config_path=str(config_file))

    response = json.dumps({
        "app_name": "Simple App", "app_slug": "simple-app",
        "control_skill_name": "Control", "control_skill_description": "Controls",
        "subordinate_skills": [], "reused_skills": [], "new_skills": [],
        "decomposition_plan": [], "governance_notes": [], "design_notes": "minimal",
    })

    intent = _make_intent(app_name="Simple", goal="Simple goal")
    architect = AppArchitect(router, skill_registry=None)
    with patch.object(architect, "_router") as mock_router:
        mock_router.get_client.return_value.generate_response.return_value = (response, {})
        result = architect.design(intent)

    assert result.app_name == "Simple App"


def test_architect_raises_on_parse_error(tmp_path) -> None:
    """Architect should raise AppArchitectError on unparseable response."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "strong": {"model": "gpt-5.4", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
        "routing": {"callers": {"architect": {"default_model": "strong"}}},
    }))
    router = ModelRouter(config_path=str(config_file))

    mock_client = MagicMock()
    mock_client.generate_response.return_value = ("not json at all", {})

    intent = _make_intent(app_name="Test", goal="test")
    architect = AppArchitect(router)
    with patch.object(architect, "_router") as mock_router:
        mock_router.get_client.return_value = mock_client
        with pytest.raises(AppArchitectError):
            architect.design(intent)


def test_architect_gathers_skills_from_handlers_registry(tmp_path) -> None:
    """Architect should gather skills from _handlers registry."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "strong": {"model": "gpt-5.4", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
    }))
    router = ModelRouter(config_path=str(config_file))

    mock_registry = MagicMock()
    mock_registry._handlers = {
        "skill-a": lambda: None,
        "skill-b": lambda: None,
    }

    architect = AppArchitect(router, skill_registry=mock_registry)
    skills = architect._gather_existing_skills()

    assert len(skills) >= 2


def test_architect_gathers_skills_from_entries_registry(tmp_path) -> None:
    """Architect should gather skills from _entries registry."""
    from app.services.model_router import ModelRouter
    import yaml
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "models": {
            "strong": {"model": "gpt-5.4", "base_url": "https://x.com/v1", "api_key_env": "OPENAI_API_KEY"},
        },
    }))
    router = ModelRouter(config_path=str(config_file))

    mock_entry = MagicMock()
    mock_entry.name = "Test Skill"
    mock_entry.capability_profile.intelligence_level = "high"

    mock_registry = MagicMock()
    mock_registry._handlers = {}
    mock_registry._entries = {"test-skill": mock_entry}

    architect = AppArchitect(router, skill_registry=mock_registry)
    skills = architect._gather_existing_skills()

    assert any(s["id"] == "test-skill" for s in skills)


# ===========================================================================
# AppDesignOrchestrator tests
# ===========================================================================

def test_orchestrate_analyze_intent_approved(tmp_path) -> None:
    """Orchestrator should approve clear intent."""
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = _make_intent(
        app_name="test-app", needs_clarification=False,
    )
    mock_architect = MagicMock()

    orchestrator = AppDesignOrchestrator(mock_analyzer, mock_architect)
    result = orchestrator.analyze_intent("I want a test app")

    assert result.status == "approved"
    assert result.app_name == "test-app"


def test_orchestrate_analyze_intent_needs_clarification(tmp_path) -> None:
    """Orchestrator should signal when clarification is needed."""
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = _make_intent(
        needs_clarification=True,
        clarification_questions=["What do you want?"],
    )
    mock_architect = MagicMock()

    orchestrator = AppDesignOrchestrator(mock_analyzer, mock_architect)
    result = orchestrator.analyze_intent("I want something")

    assert result.status == "needs_clarification"
    assert len(result.clarification_questions) == 1


def test_orchestrate_analyze_intent_failure(tmp_path) -> None:
    """Orchestrator should handle analyzer errors."""
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.side_effect = AppIntentAnalyzerError("broken")
    mock_architect = MagicMock()

    orchestrator = AppDesignOrchestrator(mock_analyzer, mock_architect)
    result = orchestrator.analyze_intent("test")

    assert result.status == "failed"
    assert result.error is not None


def test_orchestrate_design_app_success(tmp_path) -> None:
    """Orchestrator should complete analyze → design flow."""
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = _make_intent(
        app_name="Monitor", needs_clarification=False,
    )
    mock_architect = MagicMock()
    mock_architect.design.return_value = _make_design(
        app_name="Monitor App", app_slug="monitor-app",
    )

    orchestrator = AppDesignOrchestrator(mock_analyzer, mock_architect)
    result = orchestrator.design_app("I want a monitor")

    assert result.status == "needs_confirmation"
    assert result.app_name == "Monitor App"
    assert result.design is not None


def test_orchestrate_design_app_clarification_needed(tmp_path) -> None:
    """Orchestrator should stop at clarification step."""
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = _make_intent(
        needs_clarification=True,
        clarification_questions=["What?"],
    )
    mock_architect = MagicMock()

    orchestrator = AppDesignOrchestrator(mock_analyzer, mock_architect)
    result = orchestrator.design_app("vague request")

    assert result.status == "needs_clarification"
    mock_architect.design.assert_not_called()


def test_orchestrate_design_app_architect_error(tmp_path) -> None:
    """Orchestrator should handle architect errors."""
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = _make_intent(
        app_name="Test", needs_clarification=False,
    )
    mock_architect = MagicMock()
    mock_architect.design.side_effect = AppArchitectError("design failed")

    orchestrator = AppDesignOrchestrator(mock_analyzer, mock_architect)
    result = orchestrator.design_app("test")

    assert result.status == "failed"


def test_orchestrate_confirm_and_create_rejected(tmp_path) -> None:
    """Orchestrator should handle user rejection."""
    mock_analyzer = MagicMock()
    mock_architect = MagicMock()
    orchestrator = AppDesignOrchestrator(mock_analyzer, mock_architect)

    design = _make_design(app_name="Test App")
    confirmation = DesignConfirmation(approved=False, feedback="not what I want")

    result = orchestrator.confirm_and_create(design, confirmation)

    assert result.status == "rejected_by_user"
    assert "not what I want" in result.message


def test_orchestrate_confirm_and_create_success(tmp_path) -> None:
    """Orchestrator should create skills on approval."""
    mock_analyzer = MagicMock()
    mock_architect = MagicMock()
    mock_skill_factory = MagicMock()
    mock_skill_factory._skill_control.get_skill.side_effect = KeyError("not found")
    mock_skill_factory.create_skill.return_value = None

    orchestrator = AppDesignOrchestrator(
        mock_analyzer, mock_architect, skill_factory=mock_skill_factory,
    )

    design = _make_design(
        app_name="Test App", app_slug="test-app",
        subordinate_skills=[
            SubordinateSkillDesign(
                suggested_name="new-skill",
                responsibility="does things",
                scope="scope",
                reuse_existing=None,
            ),
        ],
        reused_skills=["existing-skill"],
    )
    confirmation = DesignConfirmation(approved=True)

    result = orchestrator.confirm_and_create(design, confirmation)

    assert result.status == "success"
    assert len(result.created_skill_ids) >= 1


def test_orchestrate_confirm_and_create_can_continue_to_blueprint_and_install(tmp_path) -> None:
    mock_analyzer = MagicMock()
    mock_architect = MagicMock()
    mock_skill_factory = MagicMock()
    mock_skill_factory._skill_control.get_skill.side_effect = KeyError("not found")
    mock_skill_factory.create_skill.return_value = None

    mock_blueprint = MagicMock()
    mock_blueprint.id = "bp.designed.test"
    mock_blueprint_builder = MagicMock()
    mock_blueprint_builder.build_blueprint_from_design.return_value = mock_blueprint

    mock_install_result = MagicMock()
    mock_install_result.install_status = "installed"
    mock_app_installer = MagicMock()
    mock_app_installer.install_app.return_value = mock_install_result

    orchestrator = AppDesignOrchestrator(
        mock_analyzer,
        mock_architect,
        skill_factory=mock_skill_factory,
        blueprint_builder=mock_blueprint_builder,
        app_installer=mock_app_installer,
    )

    design = _make_design(
        app_name="Test App", app_slug="test-app",
        subordinate_skills=[
            SubordinateSkillDesign(
                suggested_name="new-skill",
                responsibility="does things",
                scope="scope",
                reuse_existing=None,
            ),
        ],
    )

    result = orchestrator.confirm_and_create(design, DesignConfirmation(approved=True))

    mock_blueprint_builder.build_blueprint_from_design.assert_called_once()
    mock_app_installer.install_app.assert_called_once_with("bp.designed.test", user_id="system")
    assert result.status == "success"
    assert "blueprint=bp.designed.test" in result.message
    assert "install=installed" in result.message


def test_orchestrate_without_skill_factory(tmp_path) -> None:
    """Orchestrator should work without skill factory."""
    mock_analyzer = MagicMock()
    mock_architect = MagicMock()
    orchestrator = AppDesignOrchestrator(mock_analyzer, mock_architect)

    design = _make_design(
        subordinate_skills=[
            SubordinateSkillDesign(suggested_name="x", responsibility="y", scope="z"),
        ],
    )
    confirmation = DesignConfirmation(approved=True)

    result = orchestrator.confirm_and_create(design, confirmation)

    assert result.status == "success"
    assert len(result.created_skill_ids) == 0  # No skill factory
