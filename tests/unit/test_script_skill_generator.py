import json
from pathlib import Path

from app.models.generated_skill import GeneratedSkillRequest
from app.models.skill_runtime import SkillExecutionRequest
from app.services.generated_skill_asset_store import GeneratedSkillAssetStore
from app.services.script_skill_generator import ScriptSkillGenerator
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_control import SkillControlService
from app.services.skill_runtime import SkillRuntimeService


def test_generated_skill_asset_store_creates_scaffold(tmp_path: Path) -> None:
    store = GeneratedSkillAssetStore(str(tmp_path / "generated_skills"))
    asset = store.create_scaffold(
        GeneratedSkillRequest(
            skill_id="skill.generated.slugify",
            name="Generated Slugify",
            description="slugify text",
            template_type="slugify",
        )
    )

    assert Path(asset.asset_dir).exists()
    assert Path(asset.manifest_path).exists()
    assert Path(asset.schema_path).exists()
    assert Path(asset.entrypoint_path).exists()
    assert Path(asset.asset_dir, "input.schema.json").exists()
    assert Path(asset.asset_dir, "output.schema.json").exists()
    assert Path(asset.asset_dir, "error.schema.json").exists()
    manifest = json.loads(Path(asset.manifest_path).read_text())
    assert manifest["runtime_adapter"] == "executable"
    assert manifest["adapter"]["invocation_protocol"] == "json_stdio"
    assert manifest["contract"]["input_schema_ref"].endswith("input.schema.json")
    assert manifest["contract"]["output_schema_ref"].endswith("output.schema.json")
    assert manifest["contract"]["error_schema_ref"].endswith("error.schema.json")


def test_script_skill_generator_registers_and_runtime_executes_generated_skill(tmp_path: Path) -> None:
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "generated_skills"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store=asset_store, skill_control=skill_control)

    entry = generator.generate_and_register(
        GeneratedSkillRequest(
            skill_id="skill.generated.slugify",
            name="Generated Slugify",
            description="slugify text",
            template_type="slugify",
        )
    )

    assert skill_control.get_skill("skill.generated.slugify") is not None
    assert entry.origin == "generated"
    runtime = SkillRuntimeService()
    runtime.register_handler(entry.skill_id, lambda request: None, entry=entry)
    result = runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.generated.slugify",
            app_instance_id="app.generated",
            workflow_id="wf.generated",
            step_id="step.generated",
            inputs={"text": "Hello World"},
            config={},
        )
    )

    assert result.status == "completed"
    assert result.output["slug"] == "hello-world"


def test_generated_skill_contracts_validate_with_schema_registry(tmp_path: Path) -> None:
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "generated_skills"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store=asset_store, skill_control=skill_control)
    entry = generator.generate_and_register(
        GeneratedSkillRequest(
            skill_id="skill.generated.slugify",
            name="Generated Slugify",
            description="slugify text",
            template_type="slugify",
        )
    )

    schema_registry = SchemaRegistryService()
    manifest = entry.manifest
    assert manifest is not None
    schema_registry.register(manifest.contract.input_schema_ref, json.loads(Path(manifest.contract.input_schema_ref).read_text()))
    schema_registry.register(manifest.contract.output_schema_ref, json.loads(Path(manifest.contract.output_schema_ref).read_text()))
    schema_registry.register(manifest.contract.error_schema_ref, json.loads(Path(manifest.contract.error_schema_ref).read_text()))

    schema_registry.validate(manifest.contract.input_schema_ref, {"text": "Hello World"})
    schema_registry.validate(manifest.contract.output_schema_ref, {"slug": "hello-world"})
