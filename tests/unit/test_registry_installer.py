from pathlib import Path

from app.models.app_blueprint import AppBlueprint
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.services.app_config_service import AppConfigService
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.skill_control import SkillControlService


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
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        app_config_service=app_config,
        app_profile_resolver=resolver,
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
