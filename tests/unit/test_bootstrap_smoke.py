from app.bootstrap.catalog import bootstrap_demo_catalog
from app.bootstrap.runtime import build_runtime
from app.bootstrap.skills import bootstrap_builtin_skills


def test_bootstrap_demo_catalog_blueprints_are_installable() -> None:
    services = build_runtime()
    app_registry = services["app_registry"]
    app_catalog = services["app_catalog"]
    app_installer = services["app_installer"]
    skill_runtime = services["skill_runtime"]

    bootstrap_builtin_skills(skill_runtime, services)
    bootstrap_demo_catalog(app_registry, app_catalog)

    catalog_entries = app_catalog.list_apps()
    assert len(catalog_entries) >= 2

    service_install = app_installer.install_app("bp.workspace.assistant", user_id="smoke-user")
    assert service_install.install_status == "installed"
    assert service_install.status == "installed"
    assert service_install.execution_mode == "service"

    pipeline_install = app_installer.install_app("bp.pipeline.executor", user_id="smoke-user")
    assert pipeline_install.install_status == "installed"
    assert pipeline_install.status == "installed"
    assert pipeline_install.execution_mode == "pipeline"


def test_bootstrap_runtime_exposes_builtin_skills_and_demo_catalog_entries() -> None:
    services = build_runtime()
    app_registry = services["app_registry"]
    app_catalog = services["app_catalog"]
    skill_runtime = services["skill_runtime"]
    skill_control = services["skill_control"]

    bootstrap_builtin_skills(skill_runtime, services)
    bootstrap_demo_catalog(app_registry, app_catalog)

    skill_ids = {entry.skill_id for entry in skill_control.list_skills()}
    assert {"system.app_config", "system.context", "system.state", "system.audit"}.issubset(skill_ids)

    blueprint_ids = {entry.blueprint_id for entry in app_registry.list_entries()}
    assert {"bp.workspace.assistant", "bp.pipeline.executor"}.issubset(blueprint_ids)

    catalog_ids = {entry.app_id for entry in app_catalog.list_apps()}
    assert {"app.workspace.assistant", "app.pipeline.executor"}.issubset(catalog_ids)
