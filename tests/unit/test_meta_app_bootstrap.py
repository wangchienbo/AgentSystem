from app.models.meta_app_skill import MetaAppSkillRequest
from app.services.meta_app.bootstrap import MetaAppBootstrapService


def test_meta_app_bootstrap_generates_control_skill_for_simple_app() -> None:
    service = MetaAppBootstrapService()
    result = service.bootstrap(
        MetaAppSkillRequest(
            app_name="Demo Builder",
            goal="Create a managed demo app",
            app_kind="service",
            complexity="simple",
        )
    )

    assert result.app_name == "Demo Builder"
    assert result.app_slug == "demo-builder"
    assert result.anchor_file == "DEMO-BUILDER_CONTROL.md"
    assert result.control_skill.skill_id == "demo-builder-control"
    assert "app-control" in result.control_skill.tags
    # Simple app should have at least 1 subordinate (domain-models)
    assert len(result.subordinate_suggestions) >= 1
    assert len(result.decomposition_plan) >= 3
    assert len(result.governance_notes) >= 2


def test_meta_app_bootstrap_generates_more_subordinates_for_complex_app() -> None:
    service = MetaAppBootstrapService()
    result = service.bootstrap(
        MetaAppSkillRequest(
            app_name="Data Pipeline",
            goal="Run complex data processing pipelines",
            app_kind="pipeline",
            complexity="complex",
        )
    )

    assert result.app_slug == "data-pipeline"
    assert result.control_skill.skill_id == "data-pipeline-control"
    # Complex app should have domain-models + services + api + tests
    assert len(result.subordinate_suggestions) >= 4
    assert len(result.decomposition_plan) >= 5
