from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerService
from app.services.app_registry import AppRegistryService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.app_config_service import AppConfigService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.skill_control import SkillControlService
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion


client = TestClient(app)


def build_blueprint(execution_mode: str = "service") -> AppBlueprint:
    return AppBlueprint(
        id="bp.test.registry",
        name="Registry Test App",
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
    installer = AppInstallerService(registry=registry, lifecycle=lifecycle, runtime_host=runtime, data_store=data_store, app_config_service=app_config, app_profile_resolver=resolver)
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


def test_registry_and_install_api_flow() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.api.registry",
            "name": "API Registry App",
            "goal": "registry api flow",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [{"id": "wf.api", "name": "api flow", "triggers": ["manual"], "steps": []}],
            "views": [],
            "required_modules": ["state.get"],
            "required_skills": [],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive"
            }
        },
    )
    assert register_response.status_code == 200

    list_response = client.get("/registry/apps")
    assert list_response.status_code == 200
    registry_entry = next(item for item in list_response.json() if item["blueprint_id"] == "bp.api.registry")
    assert registry_entry["release_status"] == "active"
    assert registry_entry["releases"][0]["status"] == "active"

    releases_response = client.get("/registry/apps/bp.api.registry/releases")
    assert releases_response.status_code == 200
    assert releases_response.json()[0]["version"] == "0.1.0"
    assert releases_response.json()[0]["status"] == "active"

    draft_release = client.post(
        "/registry/apps/bp.api.registry/releases",
        json={"version": "0.2.0", "note": "staged rollout", "reviewer": "alice", "activate_immediately": False},
    )
    assert draft_release.status_code == 200
    assert draft_release.json()["version"] == "0.1.0"
    assert draft_release.json()["releases"][1]["status"] == "draft"

    activated = client.post(
        "/registry/apps/bp.api.registry/releases/0.2.0/activate",
        json={"reviewer": "bob"},
    )
    assert activated.status_code == 200
    assert activated.json()["version"] == "0.2.0"
    assert activated.json()["release_note"] == "staged rollout"
    assert activated.json()["reviewer"] == "bob"

    releases_after = client.get("/registry/apps/bp.api.registry/releases")
    assert releases_after.status_code == 200
    assert [item["status"] for item in releases_after.json()] == ["superseded", "active"]

    history_after_activate = client.get("/registry/apps/bp.api.registry/release-history")
    assert history_after_activate.status_code == 200
    history_after_activate_payload = history_after_activate.json()
    assert history_after_activate_payload["active_version"] == "0.2.0"
    assert history_after_activate_payload["active_release_status"] == "active"
    assert history_after_activate_payload["total_releases"] == 2
    assert history_after_activate_payload["draft_release_count"] == 0
    assert history_after_activate_payload["superseded_release_count"] == 1
    assert history_after_activate_payload["rolled_back_release_count"] == 0
    assert history_after_activate_payload["latest_release_version"] == "0.2.0"
    assert history_after_activate_payload["latest_draft_version"] is None
    assert history_after_activate_payload["rollback_target_version"] == "0.1.0"
    assert history_after_activate_payload["releases"][0]["version"] == "0.2.0"

    compare_response = client.get(
        "/registry/apps/bp.api.registry/compare",
        params={"from_version": "0.1.0", "to_version": "0.2.0"},
    )
    assert compare_response.status_code == 200
    compare_payload = compare_response.json()
    assert compare_payload["active_version"] == "0.2.0"
    assert compare_payload["active_is_from"] is False
    assert compare_payload["active_is_to"] is True
    assert compare_payload["from_status"] == "superseded"
    assert compare_payload["to_status"] == "active"
    assert compare_payload["from_note"] == ""
    assert compare_payload["to_note"] == "staged rollout"
    assert compare_payload["to_reviewer"] == "bob"
    assert compare_payload["release_note_changed"] is True
    assert compare_payload["required_skills_added"] == []
    assert compare_payload["required_skills_removed"] == []
    assert compare_payload["runtime_policy_changes"] == {}
    assert compare_payload["runtime_profile_changes"] == {}
    assert compare_payload["app_shape_from"] == "generic"
    assert compare_payload["app_shape_to"] == "generic"
    assert "release_note" in compare_payload["changed_fields"]
    assert compare_payload["change_count"] >= 1
    assert compare_payload["summary"].startswith("Changed:")

    install_response = client.post(
        "/registry/apps/bp.api.registry/install",
        json={"user_id": "api-user"},
    )
    assert install_response.status_code == 200
    assert install_response.json()["execution_mode"] == "service"
    assert install_response.json()["release_version"] == "0.2.0"
    assert install_response.json()["runtime_profile"]["offline_capable"] is True

    rolled_back = client.post(
        "/registry/apps/bp.api.registry/rollback",
        json={"target_version": "0.1.0", "reviewer": "carol", "rollback_reason": "staged release regression"},
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["version"] == "0.1.0"
    assert rolled_back.json()["rollback_reason"] == "staged release regression"
    assert rolled_back.json()["reviewer"] == "carol"

    releases_final = client.get("/registry/apps/bp.api.registry/releases")
    assert releases_final.status_code == 200
    assert [item["status"] for item in releases_final.json()] == ["active", "rolled_back"]
    assert releases_final.json()[0]["rollback_reason"] == "staged release regression"

    reinstall_response = client.post(
        "/registry/apps/bp.api.registry/install",
        json={"user_id": "api-user-rollback"},
    )
    assert reinstall_response.status_code == 200
    assert reinstall_response.json()["release_version"] == "0.1.0"
