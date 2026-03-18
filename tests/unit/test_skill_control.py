import pytest

from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillManifest, SkillContractRef
from app.services.skill_control import SkillControlError, SkillControlService


def build_entry(skill_id: str = "router.skill", immutable: bool = False) -> SkillRegistryEntry:
    return SkillRegistryEntry(
        skill_id=skill_id,
        name="Requirement Router",
        immutable_interface=immutable,
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="initial")],
        dependencies=["experience.index"],
        capability_profile=SkillCapabilityProfile(
            intelligence_level="L1_assisted",
            network_requirement="N0_none",
            runtime_criticality="C0_build_only",
            execution_locality="local",
            invocation_default="ask_user",
            risk_level="R0_safe_read",
        ),
        runtime_adapter="callable",
        manifest=SkillManifest(
            skill_id=skill_id,
            name="Requirement Router",
            version="1.0.0",
            description="builder assistance",
            runtime_adapter="callable",
            contract=SkillContractRef(),
            tags=["builder"],
        ),
    )


def test_list_and_get_skills() -> None:
    service = SkillControlService()
    service.register(build_entry())

    skills = service.list_skills()

    assert len(skills) == 1
    assert service.get_skill("router.skill").active_version == "1.0.0"
    assert service.get_skill("router.skill").capability_profile.intelligence_level == "L1_assisted"
    assert service.get_skill("router.skill").manifest is not None


def test_replace_skill_creates_new_active_version() -> None:
    service = SkillControlService()
    service.register(build_entry())

    result = service.replace_skill("router.skill", "1.1.0", "updated", note="improve routing")

    assert result.action == "replace"
    assert result.active_version == "1.1.0"
    assert service.get_skill("router.skill").active_version == "1.1.0"


def test_rollback_skill_switches_active_version() -> None:
    service = SkillControlService()
    entry = build_entry()
    entry.versions.append(SkillVersion(version="1.1.0", content="updated"))
    entry.active_version = "1.1.0"
    entry.manifest.version = "1.1.0"
    service.register(entry)

    result = service.rollback_skill("router.skill", "1.0.0")

    assert result.action == "rollback"
    assert result.active_version == "1.0.0"
    assert result.status == "rollback_ready"


def test_disable_and_enable_skill() -> None:
    service = SkillControlService()
    service.register(build_entry())

    disabled = service.disable_skill("router.skill")
    enabled = service.enable_skill("router.skill")

    assert disabled.status == "disabled"
    assert enabled.status == "active"


def test_register_rejects_inconsistent_manifest() -> None:
    service = SkillControlService()
    entry = build_entry()
    entry.manifest.version = "9.9.9"

    with pytest.raises(SkillControlError):
        service.register(entry)


def test_immutable_skill_cannot_be_modified() -> None:
    service = SkillControlService()
    service.register(build_entry(skill_id="core.skill.interface", immutable=True))

    with pytest.raises(SkillControlError):
        service.replace_skill("core.skill.interface", "2.0.0", "danger")


from fastapi.testclient import TestClient
from app.api.main import app


def test_get_unknown_skill_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/skills/unknown.skill")

    assert response.status_code == 404


def test_replace_immutable_skill_returns_400() -> None:
    client = TestClient(app)

    response = client.post(
        "/skills/core.skill.control/replace",
        json={"version": "2.0.0", "content": "danger"},
    )

    assert response.status_code == 400
