from pathlib import Path

from app.models.skill_creation import SkillCreationRequest, SkillSchemaDefinition
from app.models.skill_runtime import SkillExecutionRequest
from app.services.app_data_store import AppDataStore
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_control import SkillControlService
from app.services.skill_factory import SkillFactoryService
from app.services.skill_runtime import SkillRuntimeService


def test_generated_script_skill_persists_and_reloads(tmp_path: Path) -> None:
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

    request = SkillCreationRequest(
        skill_id="skill.text.slugify.persisted",
        name="Persisted Slugify Skill",
        description="persisted generated script skill",
        adapter_kind="script",
        command=["python3", "tests/fixtures/script_slugify_skill.py"],
        schemas=SkillSchemaDefinition(
            input={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            output={
                "type": "object",
                "properties": {
                    "source_text": {"type": "string"},
                    "slug": {"type": "string"},
                    "length": {"type": "integer"},
                    "adapter": {"type": "string"},
                },
                "required": ["source_text", "slug", "length", "adapter"],
                "additionalProperties": True,
            },
            error={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            },
        ),
        smoke_test_inputs={"text": "Persist Me Please"},
    )

    created = factory.create_skill(request)
    assert created.smoke_test.status == "completed"
    assert created.smoke_test.output["slug"] == "persist-me-please"
    assert len(generated_assets.list_generated_assets()) == 1

    reloaded_schema_registry = SchemaRegistryService()
    reloaded_skill_control = SkillControlService()
    reloaded_skill_runtime = SkillRuntimeService(store=runtime_store, schema_registry=reloaded_schema_registry)
    reloaded_assets = GeneratedSkillAssetStore(data_store)
    reloaded_factory = SkillFactoryService(
        skill_control=reloaded_skill_control,
        skill_runtime=reloaded_skill_runtime,
        schema_registry=reloaded_schema_registry,
        generated_assets=reloaded_assets,
    )

    restored = reloaded_factory.reload_generated_skills()
    assert restored == 1
    restored_entry = reloaded_skill_control.get_skill("skill.text.slugify.persisted")
    assert restored_entry.manifest is not None
    assert restored_entry.runtime_adapter == "script"

    result = reloaded_skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.text.slugify.persisted",
            app_instance_id="persisted-app",
            workflow_id="wf.persisted",
            step_id="slugify",
            inputs={"text": "Reloaded Skill Works"},
            config={},
        )
    )

    assert result.status == "completed"
    assert result.output["slug"] == "reloaded-skill-works"
