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


FIXTURE_PATH = Path("/root/project/AgentSystem/tests/fixtures/script_slugify_skill.py")


def test_generated_skill_assets_reload_after_runtime_rebuild(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "app-data"), store=store)
    schema_registry = SchemaRegistryService()
    skill_control = SkillControlService()
    skill_runtime = SkillRuntimeService(store=store, schema_registry=schema_registry)
    generated_assets = GeneratedSkillAssetStore(data_store)
    factory = SkillFactoryService(
        skill_control=skill_control,
        skill_runtime=skill_runtime,
        schema_registry=schema_registry,
        generated_assets=generated_assets,
    )

    request = SkillCreationRequest(
        skill_id="skill.text.slugify.durable",
        name="Durable Slugify Skill",
        description="persists and reloads across runtime rebuilds",
        adapter_kind="script",
        command=["python3", str(FIXTURE_PATH)],
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
        smoke_test_inputs={"text": "Hello Durable Runtime"},
    )

    created = factory.create_skill(request)
    assert created.runtime_adapter == "script"
    assert any(asset["skill_id"] == "skill.text.slugify.durable" for asset in generated_assets.list_generated_assets())

    rebuilt_schema_registry = SchemaRegistryService()
    rebuilt_skill_control = SkillControlService()
    rebuilt_skill_runtime = SkillRuntimeService(store=store, schema_registry=rebuilt_schema_registry)
    rebuilt_factory = SkillFactoryService(
        skill_control=rebuilt_skill_control,
        skill_runtime=rebuilt_skill_runtime,
        schema_registry=rebuilt_schema_registry,
        generated_assets=GeneratedSkillAssetStore(data_store),
    )

    restored = rebuilt_factory.reload_generated_skills()
    assert restored >= 1
    restored_entry = rebuilt_skill_control.get_skill("skill.text.slugify.durable")
    assert restored_entry.skill_id == "skill.text.slugify.durable"

    result = rebuilt_skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.text.slugify.durable",
            app_instance_id="durable-app",
            workflow_id="wf.durable",
            step_id="skill.1",
            inputs={"text": "A Durable App OS"},
            config={},
        )
    )
    assert result.status == "completed"
    assert result.output["slug"] == "a-durable-app-os"
    assert result.output["adapter"] == "script"
