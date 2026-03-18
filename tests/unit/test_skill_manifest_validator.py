import pytest

from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest
from app.models.skill_adapter import SkillAdapterSpec
from app.services.skill_manifest_validator import SkillManifestValidationError, SkillManifestValidatorService


def build_entry() -> SkillRegistryEntry:
    return SkillRegistryEntry(
        skill_id="system.test",
        name="System Test",
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="ok")],
        dependencies=[],
        capability_profile=SkillCapabilityProfile(),
        runtime_adapter="callable",
        manifest=SkillManifest(
            skill_id="system.test",
            name="System Test",
            version="1.0.0",
            description="validator test",
            runtime_adapter="callable",
            adapter=SkillAdapterSpec(kind="callable", entry="app.handlers:test"),
            contract=SkillContractRef(input_schema_ref="", output_schema_ref="", error_schema_ref=""),
            tags=["system"],
        ),
    )


def test_manifest_validator_accepts_consistent_entry() -> None:
    validator = SkillManifestValidatorService()
    validator.validate(build_entry())


def test_manifest_validator_rejects_mismatched_adapter() -> None:
    validator = SkillManifestValidatorService()
    entry = build_entry()
    entry.manifest.runtime_adapter = "script"

    with pytest.raises(SkillManifestValidationError):
        validator.validate(entry)
