from pathlib import Path

import pytest

from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest, SkillManifestRisk
from app.models.skill_adapter import SkillAdapterSpec
from app.services.schema_registry import SchemaRegistryService
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


def test_manifest_validator_accepts_registered_contract_refs() -> None:
    registry = SchemaRegistryService()
    registry.register("schema://system.test/input", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False})
    registry.register("schema://system.test/output", {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False})
    entry = build_entry()
    entry.manifest.contract = SkillContractRef(
        input_schema_ref="schema://system.test/input",
        output_schema_ref="schema://system.test/output",
        error_schema_ref="",
    )

    validator = SkillManifestValidatorService(schema_registry=registry)
    validator.validate(entry)


def test_manifest_validator_rejects_missing_contract_ref() -> None:
    registry = SchemaRegistryService()
    entry = build_entry()
    entry.manifest.contract = SkillContractRef(
        input_schema_ref="schema://system.test/input",
        output_schema_ref="",
        error_schema_ref="",
    )

    validator = SkillManifestValidatorService(schema_registry=registry)
    with pytest.raises(SkillManifestValidationError, match="Schema ref not found"):
        validator.validate(entry)


def test_manifest_validator_rejects_disallowed_script_command_prefix() -> None:
    validator = SkillManifestValidatorService()
    entry = build_entry()
    entry.runtime_adapter = "script"
    entry.manifest.runtime_adapter = "script"
    entry.manifest.adapter = SkillAdapterSpec(kind="script", command=["curl", "https://example.com"])

    with pytest.raises(SkillManifestValidationError, match="command prefix not allowed"):
        validator.validate(entry)


def test_manifest_validator_requires_shell_risk_opt_in_for_shell_scripts() -> None:
    validator = SkillManifestValidatorService()
    entry = build_entry()
    entry.runtime_adapter = "script"
    entry.manifest.runtime_adapter = "script"
    entry.manifest.adapter = SkillAdapterSpec(kind="script", command=["bash", "script.sh"])
    entry.manifest.risk = SkillManifestRisk(allow_shell=False)

    with pytest.raises(SkillManifestValidationError, match="require risk.allow_shell=true"):
        validator.validate(entry)


def test_manifest_validator_accepts_shell_script_with_explicit_risk_opt_in() -> None:
    validator = SkillManifestValidatorService()
    entry = build_entry()
    entry.runtime_adapter = "script"
    entry.manifest.runtime_adapter = "script"
    entry.manifest.adapter = SkillAdapterSpec(kind="script", command=["bash", "script.sh"])
    entry.manifest.risk = SkillManifestRisk(allow_shell=True, risk_level="R2_shell")

    validator.validate(entry)


def test_manifest_validator_rejects_missing_executable_entrypoint(tmp_path: Path) -> None:
    validator = SkillManifestValidatorService()
    entry = build_entry()
    entry.runtime_adapter = "executable"
    entry.manifest.runtime_adapter = "executable"
    entry.manifest.adapter = SkillAdapterSpec(
        kind="executable",
        command=["python3"],
        entry=str(tmp_path / "missing.py"),
        invocation_protocol="json_stdio",
    )

    with pytest.raises(SkillManifestValidationError, match="entrypoint not found"):
        validator.validate(entry)
