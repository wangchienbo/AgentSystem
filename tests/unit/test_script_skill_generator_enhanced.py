"""Tests for enhanced ScriptSkillGenerator: auto-description, smoke test, validation."""

import json
from pathlib import Path

from app.models.generated_skill import GeneratedSkillRequest
from app.models.skill_runtime import SkillExecutionRequest
from app.services.generated_skill_asset_store import GeneratedSkillAssetStore
from app.services.script_skill_generator import ScriptSkillGenerator, ScriptSkillGenerationError
from app.services.skill_control import SkillControlService
from app.services.skill_runtime import SkillRuntimeService


def test_auto_description_from_skill_id_and_name(tmp_path: Path) -> None:
    """Description is auto-generated when not provided."""
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "gen"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store, skill_control)

    request = GeneratedSkillRequest(
        skill_id="skill.generated.my_tool",
        name="My Tool",
        description="",  # empty → auto-generate
        template_type="text_transform",
    )
    enriched = generator._enrich_request(request)
    assert enriched.description != ""
    assert "My Tool" in enriched.description
    assert "text_transform" in enriched.description
    assert "my tool" in enriched.description.lower()


def test_auto_description_preserves_user_description(tmp_path: Path) -> None:
    """User-provided description is kept as-is."""
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "gen"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store, skill_control)

    request = GeneratedSkillRequest(
        skill_id="skill.generated.my_tool",
        name="My Tool",
        description="User provided description",
        template_type="text_transform",
    )
    enriched = generator._enrich_request(request)
    assert enriched.description == "User provided description"


def test_generate_and_register_auto_description(tmp_path: Path) -> None:
    """Full generation with auto-generated description."""
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "gen"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store, skill_control)

    entry = generator.generate_and_register(
        GeneratedSkillRequest(
            skill_id="skill.gen.auto_desc",
            name="Auto Desc Skill",
            description="",  # empty
            template_type="slugify",
        ),
        run_smoke_test=False,
    )

    assert entry.manifest is not None
    assert entry.manifest.description != ""
    assert "Auto Desc Skill" in entry.manifest.description


def test_generate_and_register_smoke_test_passes(tmp_path: Path) -> None:
    """Full generation with smoke test execution (slugify template passes)."""
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "gen"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store, skill_control)

    entry = generator.generate_and_register(
        GeneratedSkillRequest(
            skill_id="skill.gen.smoke_test",
            name="Smoke Test Skill",
            description="Test smoke test",
            template_type="slugify",
        ),
        run_smoke_test=True,
    )

    assert entry.skill_id == "skill.gen.smoke_test"
    assert entry.origin == "generated"


def test_scaffold_validation_catches_missing_file(tmp_path: Path) -> None:
    """Validation raises error when scaffold files are missing."""
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "gen"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store, skill_control)

    asset = asset_store.create_scaffold(
        GeneratedSkillRequest(
            skill_id="skill.gen.validate",
            name="Validate Skill",
            description="test",
            template_type="slugify",
        )
    )

    # Delete a required file
    Path(asset.manifest_path).unlink()

    try:
        generator._validate_scaffold(asset)
    except ScriptSkillGenerationError as error:
        assert "missing" in str(error).lower()
    else:
        raise AssertionError("expected ScriptSkillGenerationError")


def test_generated_skill_callable_via_runtime(tmp_path: Path) -> None:
    """Generated skill can be registered and executed through the runtime."""
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "gen"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store, skill_control)

    entry = generator.generate_and_register(
        GeneratedSkillRequest(
            skill_id="skill.gen.runtime",
            name="Runtime Skill",
            description="runtime test",
            template_type="slugify",
        ),
        run_smoke_test=False,
    )

    runtime = SkillRuntimeService()
    runtime.register_handler(entry.skill_id, lambda request: None, entry=entry)
    result = runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.gen.runtime",
            app_instance_id="app.test",
            workflow_id="wf.test",
            step_id="step.test",
            inputs={"text": "Test Input"},
            config={},
        )
    )

    assert result.status == "completed"
    assert result.output["slug"] == "test-input"


def test_manifest_contains_complete_adapter_and_contract(tmp_path: Path) -> None:
    """Verify generated manifest has complete adapter and contract sections."""
    asset_store = GeneratedSkillAssetStore(str(tmp_path / "gen"))
    skill_control = SkillControlService()
    generator = ScriptSkillGenerator(asset_store, skill_control)

    entry = generator.generate_and_register(
        GeneratedSkillRequest(
            skill_id="skill.gen.complete",
            name="Complete Skill",
            description="complete test",
            template_type="slugify",
        ),
        run_smoke_test=False,
    )

    manifest = entry.manifest
    assert manifest is not None

    # Adapter completeness
    adapter = manifest.adapter
    assert adapter.kind == "executable"
    assert adapter.invocation_protocol == "json_stdio"
    assert adapter.timeout_seconds > 0

    # Contract completeness
    contract = manifest.contract
    assert contract.input_schema_ref
    assert contract.output_schema_ref
    assert contract.error_schema_ref
    assert Path(contract.input_schema_ref).exists()
    assert Path(contract.output_schema_ref).exists()
    assert Path(contract.error_schema_ref).exists()
