from app.models.skill_control import SkillCapabilityProfile
from app.services.skill_authoring import SkillAuthoringService, SkillAuthoringSpec


def test_skill_authoring_service_builds_callable_entry() -> None:
    service = SkillAuthoringService()

    entry = service.build_callable_entry(
        skill_id="skill.notes.append",
        name="Notes Append",
        handler_entry="app.skills.notes:append_note",
        description="append a note into app-local notes",
        input_schema_ref="schema://skill.notes.append/input",
        output_schema_ref="schema://skill.notes.append/output",
        error_schema_ref="schema://skill.notes.append/error",
        tags=["notes", "deterministic"],
    )

    assert entry.skill_id == "skill.notes.append"
    assert entry.runtime_adapter == "callable"
    assert entry.manifest is not None
    assert entry.manifest.adapter.kind == "callable"
    assert entry.manifest.adapter.entry == "app.skills.notes:append_note"
    assert entry.manifest.contract.input_schema_ref == "schema://skill.notes.append/input"
    assert entry.manifest.tags == ["notes", "deterministic"]
    assert entry.origin == "manual"


def test_skill_authoring_service_builds_script_entry() -> None:
    service = SkillAuthoringService()

    entry = service.build_script_entry(
        skill_id="skill.shell.echo",
        name="Shell Echo",
        command=["python3", "tests/fixtures/script_echo_skill.py"],
        description="echo text through script adapter",
        tags=["script"],
    )

    assert entry.runtime_adapter == "script"
    assert entry.manifest is not None
    assert entry.manifest.adapter.kind == "script"
    assert entry.manifest.adapter.command == ["python3", "tests/fixtures/script_echo_skill.py"]
    assert entry.manifest.tags == ["script"]
    assert entry.origin == "manual"


def test_skill_authoring_service_preserves_capability_profile_and_dependencies() -> None:
    service = SkillAuthoringService()
    capability = SkillCapabilityProfile(
        intelligence_level="L1_assisted",
        network_requirement="N1_optional",
        runtime_criticality="C1_optional_runtime",
        execution_locality="hybrid",
        invocation_default="ask_user",
        risk_level="R2_network_call",
    )

    entry = service.build_entry(
        SkillAuthoringSpec(
            skill_id="skill.assisted.lookup",
            name="Assisted Lookup",
            description="optional model-assisted lookup",
            runtime_adapter="callable",
            adapter_entry="app.skills.lookup:run",
            dependencies=["module.http"],
            capability_profile=capability,
        )
    )

    assert entry.dependencies == ["module.http"]
    assert entry.capability_profile == capability
    assert entry.manifest is not None
    assert entry.manifest.description == "optional model-assisted lookup"
    assert entry.origin == "manual"
