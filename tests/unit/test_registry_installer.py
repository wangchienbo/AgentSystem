from pathlib import Path

from app.models.app_blueprint import AppBlueprint
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.app_design import AppDesignResult, DesignConfirmation, SubordinateSkillDesign
from app.services.app_config_service import AppConfigService
from app.services.app_data_store import AppDataStore
from app.services.app_designer.orchestrator import AppDesignOrchestrator
from app.services.app_installer import AppInstallerService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.app_registry import AppRegistryService
from app.services.asset_center import AssetCenter
from app.services.design_blueprint_builder import DesignBlueprintBuilderService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.skill_control import SkillControlService


def _make_design(**overrides) -> AppDesignResult:
    return AppDesignResult(
        app_name=overrides.get("app_name", "Test App"),
        app_slug=overrides.get("app_slug", "test-app"),
        control_skill_name=overrides.get("control_skill_name", "Test Control"),
        control_skill_description=overrides.get("control_skill_description", "Controls test"),
        **{k: v for k, v in overrides.items() if k not in (
            "app_name", "app_slug", "control_skill_name", "control_skill_description"
        )},
    )


    return AppBlueprint(
        id=blueprint_id,
        name=name,
        goal="verify registry and installer",
        roles=[],
        tasks=[],
        workflows=[{"id": "wf.test", "name": "test", "triggers": ["manual"], "steps": []}],
        required_modules=["state.get"],
        required_skills=[],
        runtime_policy={
            "execution_mode": execution_mode,
            "activation": "on_demand",
            "restart_policy": "on_failure",
            "persistence_level": "standard",
            "idle_strategy": "suspend",
        },
    )


def test_registry_registers_blueprint(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "registry-store"))
    registry = AppRegistryService(store=store)

    entry = registry.register_blueprint(build_blueprint(), description="registry test")

    assert entry.blueprint_id == "bp.test.registry"
    assert entry.release_status == "active"
    assert entry.releases[0].version == "0.1.0"
    assert entry.releases[0].status == "active"
    assert registry.get_blueprint("bp.test.registry").runtime_policy.execution_mode == "service"


def test_app_design_confirm_registers_blueprint_before_real_install(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "designer-installer-store"))
    registry = AppRegistryService(store=store)
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "designer-installer-ns"), store=store)
    app_config = AppConfigService(data_store=data_store, store=store)
    skill_control = SkillControlService()
    for skill_id in [
        "system.app_config",
        "system.context",
        "system.state",
        "system.audit",
        "monitor.collect",
        "monitor.control",
    ]:
        skill_control.register(
            SkillRegistryEntry(
                skill_id=skill_id,
                name=skill_id,
                immutable_interface=True,
                active_version="1.0.0",
                versions=[SkillVersion(version="1.0.0", content=skill_id)],
                dependencies=[],
                capability_profile=SkillCapabilityProfile(
                    intelligence_level="L0_deterministic",
                    network_requirement="N0_none",
                    runtime_criticality="C2_required_runtime",
                    execution_locality="local",
                    invocation_default="automatic",
                    risk_level="R1_local_write",
                ),
                runtime_adapter="callable",
            )
        )
    resolver = AppProfileResolverService(skill_control=skill_control)
    asset_center = AssetCenter(
        source_dir=str(tmp_path / "source"),
        installed_dir=str(tmp_path / "installed"),
        build_dir=str(tmp_path / "build"),
        data_dir=str(tmp_path / "asset-data"),
    )
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        app_config_service=app_config,
        app_profile_resolver=resolver,
        asset_center=asset_center,
    )

    orchestrator = AppDesignOrchestrator(
        intent_analyzer=None,
        architect=None,
        blueprint_builder=DesignBlueprintBuilderService(),
        app_registry=registry,
        app_installer=installer,
    )

    design = _make_design(
        app_name="Monitor App",
        app_slug="monitor-app",
        control_skill_name="monitor.control",
        control_skill_description="Control monitoring workflows",
        subordinate_skills=[
            SubordinateSkillDesign(
                suggested_name="monitor.collect",
                responsibility="Collect metrics",
                scope="metrics",
                reuse_existing=None,
            ),
        ],
        reused_skills=["monitor.control"],
        design_notes="Monitoring app design",
    )

    result = orchestrator.confirm_and_create(design, DesignConfirmation(approved=True))

    assert result.status == "success"
    assert result.blueprint_id == "bp.designed.monitor-app"
    assert result.install_status == "installed"
    assert result.blueprint_error == ""
    assert result.install_error == ""
    assert registry.get_blueprint("bp.designed.monitor-app").name == "Monitor App"
    instance = lifecycle.get_instance("bp.designed.monitor-app:system")
    assert instance.blueprint_id == "bp.designed.monitor-app"
    assert instance.status == "installed"
    snapshot = app_config.get_snapshot("bp.designed.monitor-app:system")
    assert snapshot.values["app"]["blueprint_id"] == "bp.designed.monitor-app"


