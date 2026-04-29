"""Tests for App Design models."""
import pytest

from app.models.app_design import (
    AppCreationResult,
    AppDesignResult,
    AppIntentResult,
    DesignConfirmation,
    SubordinateSkillDesign,
)


# ===========================================================================
# AppIntentResult
# ===========================================================================

def test_app_intent_result_defaults() -> None:
    """AppIntentResult should have sensible defaults."""
    result = AppIntentResult()
    assert result.app_name == ""
    assert result.goal == ""
    assert result.kind == "service"
    assert result.complexity == "moderate"
    assert result.constraints == []
    assert result.needs_clarification is False
    assert result.clarification_questions == []
    assert result.confidence == 0.0


def test_app_intent_result_with_values() -> None:
    """AppIntentResult should accept custom values."""
    result = AppIntentResult(
        app_name="monitoring-app",
        goal="Monitor server health",
        kind="monitoring",
        complexity="complex",
        constraints=["must be fast", "low memory"],
        needs_clarification=True,
        clarification_questions=["Which servers?", "What metrics?"],
        confidence=0.85,
    )
    assert result.app_name == "monitoring-app"
    assert result.kind == "monitoring"
    assert len(result.constraints) == 2
    assert len(result.clarification_questions) == 2
    assert result.needs_clarification is True


# ===========================================================================
# SubordinateSkillDesign
# ===========================================================================

def test_subordinate_skill_design_required_fields() -> None:
    """SubordinateSkillDesign requires suggested_name, scope, responsibility."""
    design = SubordinateSkillDesign(
        suggested_name="test-skill",
        scope="test scope",
        responsibility="test responsibility",
    )
    assert design.suggested_name == "test-skill"
    assert design.priority == "medium"
    assert design.reuse_existing is None


def test_subordinate_skill_design_with_reuse() -> None:
    """SubordinateSkillDesign can reference an existing skill to reuse."""
    design = SubordinateSkillDesign(
        suggested_name="replacement",
        scope="same scope",
        responsibility="same job",
        reuse_existing="existing-skill-id",
        priority="high",
    )
    assert design.reuse_existing == "existing-skill-id"
    assert design.priority == "high"


# ===========================================================================
# AppDesignResult
# ===========================================================================

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


def test_app_design_result_minimal() -> None:
    """AppDesignResult with minimal required fields."""
    result = _make_design()
    assert result.app_name == "Test App"
    assert result.app_slug == "test-app"
    assert result.subordinate_skills == []
    assert result.reused_skills == []


def test_app_design_result_with_subordinate_skills() -> None:
    """AppDesignResult should track subordinate skills."""
    result = _make_design(
        app_name="Monitor",
        app_slug="monitor",
        subordinate_skills=[
            SubordinateSkillDesign(
                suggested_name="cpu-monitor",
                responsibility="Monitor CPU",
                scope="cpu metrics",
            ),
        ],
        reused_skills=["existing-skill"],
    )
    assert len(result.subordinate_skills) == 1
    assert len(result.reused_skills) == 1


# ===========================================================================
# DesignConfirmation
# ===========================================================================

def test_design_confirmation_approved() -> None:
    """DesignConfirmation should support approval."""
    conf = DesignConfirmation(approved=True)
    assert conf.approved is True
    assert conf.feedback == ""


def test_design_confirmation_rejected_with_feedback() -> None:
    """DesignConfirmation should support rejection with feedback."""
    conf = DesignConfirmation(
        approved=False,
        feedback="Too complex, simplify",
    )
    assert conf.approved is False
    assert "simplify" in conf.feedback


# ===========================================================================
# AppCreationResult
# ===========================================================================

def test_app_creation_result_approved() -> None:
    """AppCreationResult for approved intent."""
    result = AppCreationResult(
        status="approved",
        app_name="test-app",
        message="Intent analyzed",
    )
    assert result.status == "approved"
    assert result.app_name == "test-app"
    assert result.design is None


def test_app_creation_result_needs_clarification() -> None:
    """AppCreationResult for clarification needed."""
    result = AppCreationResult(
        status="needs_clarification",
        clarification_questions=["What do you mean?"],
    )
    assert result.status == "needs_clarification"
    assert len(result.clarification_questions) == 1


def test_app_creation_result_needs_confirmation() -> None:
    """AppCreationResult when design is ready for confirmation."""
    design = _make_design()
    result = AppCreationResult(
        status="needs_confirmation",
        app_name="test",
        design=design,
    )
    assert result.status == "needs_confirmation"
    assert result.design is not None


def test_app_creation_result_success() -> None:
    """AppCreationResult for successful creation."""
    result = AppCreationResult(
        status="success",
        app_name="test-app",
        created_skill_ids=["skill-1", "skill-2"],
        blueprint_id="bp.test.app",
        install_status="installed",
        blueprint_error="",
        install_error="",
    )
    assert result.status == "success"
    assert len(result.created_skill_ids) == 2
    assert result.blueprint_id == "bp.test.app"
    assert result.install_status == "installed"
    assert result.blueprint_error == ""
    assert result.install_error == ""


def test_app_creation_result_rejected() -> None:
    """AppCreationResult for user rejection."""
    result = AppCreationResult(
        status="rejected_by_user",
        app_name="test-app",
        message="User said no",
    )
    assert result.status == "rejected_by_user"


def test_app_creation_result_failed() -> None:
    """AppCreationResult for failure."""
    result = AppCreationResult(
        status="failed",
        error="Something went wrong",
    )
    assert result.status == "failed"
    assert result.error == "Something went wrong"
