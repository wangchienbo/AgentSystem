from app.models.meta_app_skill import MetaAppSkillRequest
from app.services.meta_app.bootstrap import MetaAppBootstrapService


def test_meta_app_bootstrap_service_returns_expected_scaffold_names() -> None:
    service = MetaAppBootstrapService()
    result = service.bootstrap(
        MetaAppSkillRequest(
            app_name="Demo Builder",
            goal="Create a managed demo app",
            app_kind="service",
        )
    )

    assert result.app_name == "Demo Builder"
    assert result.anchor_name == "demo-builder-APP_CONTROL.md"
    assert result.project_map_name == "demo-builder-project-map.yaml"
    assert result.subordinate_registry_name == "demo-builder-subordinate-registry.yaml"
    assert len(result.module_records) >= 2
