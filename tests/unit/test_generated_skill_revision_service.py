from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_creation import GeneratedSkillRevisionRequest
from app.models.skill_manifest import SkillContractRef, SkillManifest
from app.services.app_data_store import AppDataStore
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_control import SkillControlService
from app.services.skill_factory import SkillFactoryError, SkillFactoryService
from app.services.skill_runtime import SkillRuntimeService


def test_revise_manual_skill_is_rejected(tmp_path) -> None:
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "namespaces"), store=runtime_store)
    schema_registry = SchemaRegistryService()
    skill_control = SkillControlService()
    skill_runtime = SkillRuntimeService(store=runtime_store, schema_registry=schema_registry)
    generated_assets = GeneratedSkillAssetStore(data_store)
    factory = SkillFactoryService(
        skill_control=skill_control,
        skill_runtime=skill_runtime,
        schema_registry=schema_registry,
        generated_assets=generated_assets,
    )

    manual_entry = SkillRegistryEntry(
        skill_id="skill.manual.revise.rejected",
        name="Manual Revise Rejected",
        origin="manual",
        active_version="1.0.0",
        versions=[SkillVersion(version="1.0.0", content="manual")],
        capability_profile=SkillCapabilityProfile(),
        runtime_adapter="callable",
        manifest=SkillManifest(
            skill_id="skill.manual.revise.rejected",
            name="Manual Revise Rejected",
            version="1.0.0",
            description="manual skill",
            runtime_adapter="callable",
            contract=SkillContractRef(),
        ),
    )
    skill_control.register(manual_entry)

    try:
        factory.revise_generated_skill(
            "skill.manual.revise.rejected",
            GeneratedSkillRevisionRequest(version="2.0.0", description="should fail"),
        )
        assert False, "expected SkillFactoryError"
    except SkillFactoryError as error:
        assert "Generated skill asset not found" in str(error) or "Only generated skills support revise" in str(error)
