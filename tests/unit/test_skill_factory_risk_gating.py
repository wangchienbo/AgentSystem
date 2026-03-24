from pathlib import Path

import pytest

from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_creation import AppFromSkillsRequest
from app.models.skill_manifest import SkillContractRef, SkillManifest, SkillManifestRisk
from app.services.app_data_store import AppDataStore
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_control import SkillControlService
from app.services.skill_factory import SkillFactoryError, SkillFactoryService
from app.services.skill_runtime import SkillRuntimeService


def _entry(skill_id: str, *, risk_level: str = "R0_safe_read", allow_shell: bool = False) -> SkillRegistryEntry:
    return SkillRegistryEntry(
        skill_id=skill_id,
        name=skill_id,
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="ok")],
        dependencies=[],
        capability_profile=SkillCapabilityProfile(risk_level=risk_level),
        runtime_adapter="script",
        manifest=SkillManifest(
            skill_id=skill_id,
            name=skill_id,
            version="1.0.0",
            description="risk gating test",
            runtime_adapter="script",
            adapter=SkillAdapterSpec(kind="script", command=["python3", "tests/fixtures/script_echo_skill.py"]),
            contract=SkillContractRef(input_schema_ref="", output_schema_ref="", error_schema_ref=""),
            tags=["generated"],
            risk=SkillManifestRisk(risk_level=risk_level, allow_shell=allow_shell),
        ),
    )


def test_generated_app_assembly_allows_safe_skill(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "risk-gating-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "risk-gating-ns"), store=store)
    factory = SkillFactoryService(
        skill_control=SkillControlService(),
        skill_runtime=SkillRuntimeService(store=store),
        schema_registry=SchemaRegistryService(),
        generated_assets=GeneratedSkillAssetStore(data_store),
    )
    factory._skill_control.register(_entry("skill.safe.generated"))

    blueprint, result = factory.build_blueprint_from_skills(
        AppFromSkillsRequest(
            blueprint_id="bp.safe.generated",
            name="Safe Generated App",
            goal="assemble safe skill",
            skill_ids=["skill.safe.generated"],
            workflow_id="wf.safe.generated",
        )
    )

    assert blueprint.id == "bp.safe.generated"
    assert result.required_skills == ["skill.safe.generated"]


def test_generated_app_assembly_rejects_high_risk_skill(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "risk-gating-store-blocked"))
    data_store = AppDataStore(base_dir=str(tmp_path / "risk-gating-ns-blocked"), store=store)
    factory = SkillFactoryService(
        skill_control=SkillControlService(),
        skill_runtime=SkillRuntimeService(store=store),
        schema_registry=SchemaRegistryService(),
        generated_assets=GeneratedSkillAssetStore(data_store),
    )
    blocked_entry = _entry("skill.blocked.generated", risk_level="R4_networked")
    blocked_entry.manifest.risk.allow_network = True
    factory._skill_control.register(blocked_entry)

    with pytest.raises(SkillFactoryError, match="risk policy"):
        factory.build_blueprint_from_skills(
            AppFromSkillsRequest(
                blueprint_id="bp.blocked.generated",
                name="Blocked Generated App",
                goal="assemble blocked skill",
                skill_ids=["skill.blocked.generated"],
                workflow_id="wf.blocked.generated",
            )
        )
