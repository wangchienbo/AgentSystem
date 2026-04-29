from pathlib import Path
import json

from app.models.app_blueprint import AppBlueprint
from app.models.app_design import AppDesignResult, DesignConfirmation, SubordinateSkillDesign
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
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


def build_blueprint(
    execution_mode: str = "service",
    *,
    blueprint_id: str = "bp.test.registry",
    name: str = "Registry Test App",
) -> AppBlueprint:
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


def test_installer_creates_instance_with_runtime_policy(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "installer-store"))
    registry = AppRegistryService(store=store)
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "installer-ns"), store=store)
    app_config = AppConfigService(data_store=data_store, store=store)
    skill_control = SkillControlService()
    for skill_id in ["system.app_config", "system.context", "system.state", "system.audit"]:
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
    registry.register_blueprint(build_blueprint(execution_mode="pipeline"))

    result = installer.install_app("bp.test.registry", user_id="user.install")
    instance = lifecycle.get_instance(result.app_instance_id)

    assert result.status == "installed"
    assert result.app_shape == "generic"
    assert result.runtime_profile.runtime_intelligence_level == "L0_deterministic"
    assert result.runtime_profile.offline_capable is True
    assert instance.execution_mode == "pipeline"
    assert instance.runtime_policy.execution_mode == "pipeline"
    assert "system.app_config" in instance.system_skills
    assert "system.app_config" in instance.resolved_skills
    assert instance.runtime_profile.runtime_intelligence_level == "L0_deterministic"
    assert instance.runtime_profile.offline_capable is True
    snapshot = app_config.get_snapshot(result.app_instance_id)
    assert snapshot.values["app"]["blueprint_id"] == "bp.test.registry"
    assert snapshot.values["runtime"]["runtime_profile"]["offline_capable"] is True

    asset_id = "app.test.registry"
    assert asset_center.get_asset(asset_id) is not None
    assert asset_center.get_installed_version(asset_id) == "0.1.0"
    manifest = json.loads((tmp_path / "source" / asset_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dependencies"] == []
    assert (tmp_path / "installed" / asset_id / "installed.json").exists()


def test_app_install_manifest_dependencies_use_skill_asset_ids(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "installer-deps-store"))
    registry = AppRegistryService(store=store)
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "installer-deps-ns"), store=store)
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
        asset_center=asset_center,
    )
    registry.register_blueprint(
        build_blueprint(
            blueprint_id="bp.test.skilldeps",
            name="Skill Dependency App",
        ).model_copy(update={"required_skills": ["monitor.control", "skill.monitor.collect"]})
    )

    installer.install_app("bp.test.skilldeps", user_id="user.install")

    manifest = json.loads((tmp_path / "source" / "app.test.skilldeps" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dependencies"] == ["skill.monitor.control", "skill.monitor.collect"]


def test_app_install_prefers_core_skill_asset_source_when_available(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "installer-core-skill-assets-store"))
    registry = AppRegistryService(store=store)
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "installer-core-skill-assets-ns"), store=store)
    asset_center = AssetCenter(
        source_dir=str(tmp_path / "source"),
        installed_dir=str(tmp_path / "installed"),
        build_dir=str(tmp_path / "build"),
        data_dir=str(tmp_path / "asset-data"),
    )
    skill_control = SkillControlService()
    skill_control.register(
        SkillRegistryEntry(
            skill_id="monitor.control",
            name="monitor.control",
            immutable_interface=True,
            active_version="1.0.0",
            versions=[SkillVersion(version="1.0.0", content="monitor.control")],
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
    core_dir = tmp_path / "installer-core-skill-assets-ns" / "skill_assets" / "core" / "executable" / "monitor_control"
    core_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / "manifest.json").write_text(json.dumps({
        "skill_id": "monitor.control",
        "name": "Core Monitor Control",
        "version": "9.9.9",
        "description": "core asset description",
        "runtime_adapter": "executable",
        "adapter": {"kind": "executable", "command": ["python3"], "entry": str(core_dir / "main.py")},
        "contract": {},
        "tags": ["core"],
        "risk": {"risk_level": "R1_local_write"}
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (core_dir / "metadata.json").write_text(json.dumps({
        "skill_id": "monitor.control",
        "asset_slug": "monitor_control",
        "asset_status": "core",
        "asset_origin": "generated",
        "runtime_adapter": "executable",
        "version": "9.9.9",
        "content_maturity": "complete"
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (core_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (core_dir / "README.md").write_text("# Core monitor control\n", encoding="utf-8")
    (core_dir / "input.schema.json").write_text("{}", encoding="utf-8")
    (core_dir / "output.schema.json").write_text("{}", encoding="utf-8")
    (core_dir / "error.schema.json").write_text("{}", encoding="utf-8")

    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        asset_center=asset_center,
        skill_control=skill_control,
    )
    registry.register_blueprint(
        build_blueprint(
            blueprint_id="bp.test.corepreferred",
            name="Core Preferred App",
        ).model_copy(update={"required_skills": ["monitor.control"]})
    )

    installer.install_app("bp.test.corepreferred", user_id="user.install")

    manifest = json.loads((tmp_path / "source" / "skill.monitor.control" / "manifest.json").read_text(encoding="utf-8"))
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
        skill_control=skill_control,
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
