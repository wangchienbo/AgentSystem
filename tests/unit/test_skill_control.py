import pytest

from app.models.skill_control import SkillRegistryEntry, SkillVersion
from app.services.skill_control import SkillControlError, SkillControlService


def build_entry(skill_id: str = "router.skill", immutable: bool = False) -> SkillRegistryEntry:
    return SkillRegistryEntry(
        skill_id=skill_id,
        name="Requirement Router",
        immutable_interface=immutable,
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="initial")],
        dependencies=["experience.index"],
    )


def test_list_and_get_skills() -> None:
    service = SkillControlService()
    service.register(build_entry())

    skills = service.list_skills()

    assert len(skills) == 1
    assert service.get_skill("router.skill").active_version == "1.0.0"


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


def test_immutable_skill_cannot_be_modified() -> None:
    service = SkillControlService()
    service.register(build_entry(skill_id="core.skill.interface", immutable=True))

    with pytest.raises(SkillControlError):
        service.replace_skill("core.skill.interface", "2.0.0", "danger")
