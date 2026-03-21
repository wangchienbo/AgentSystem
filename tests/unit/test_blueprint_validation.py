from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.app_blueprint import AppBlueprint
from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest
from app.services.app_data_store import AppDataStore
from app.services.app_installer import AppInstallerError, AppInstallerService
from app.services.app_profile_resolver import AppProfileResolverService
from app.services.app_registry import AppRegistryService
from app.services.app_config_service import AppConfigService
from app.services.blueprint_validation import BlueprintValidationService
from app.services.lifecycle import AppLifecycleService
from app.services.runtime_host import AppRuntimeHostService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_control import SkillControlService
from app.services.skill_validation import SkillValidationService


client = TestClient(app)


def _register_skill(
    skill_control: SkillControlService,
    skill_id: str,
    criticality: str = "C2_required_runtime",
    input_ref: str = "",
    output_ref: str = "",
) -> None:
    skill_control.register(
        SkillRegistryEntry(
            skill_id=skill_id,
            name=skill_id,
            immutable_interface=True,
            active_version="1.0.0",
            versions=[SkillVersion(version="1.0.0", content=skill_id)],
            dependencies=[],
            capability_profile=SkillCapabilityProfile(
                intelligence_level="L0_deterministic",
                network_requirement="N0_none",
                runtime_criticality=criticality,
                execution_locality="local",
                invocation_default="automatic",
                risk_level="R1_local_write",
            ),
            runtime_adapter="callable",
            manifest=SkillManifest(
                skill_id=skill_id,
                name=skill_id,
                version="1.0.0",
                description="validation test",
                runtime_adapter="callable",
                adapter=SkillAdapterSpec(kind="callable", entry=f"handlers:{skill_id}"),
                contract=SkillContractRef(input_schema_ref=input_ref, output_schema_ref=output_ref, error_schema_ref=""),
                tags=["test"],
            ) if input_ref or output_ref else None,
        )
    )


def test_blueprint_validation_missing_fields() -> None:
    payload = {
        "id": "bp_001",
        "name": "Test Blueprint",
        "goal": "Create an app",
        "roles": [],
        "tasks": [],
        "workflows": [],
        "views": [],
        "required_modules": [],
        "required_skills": []
    }
    response = client.post("/blueprints/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "roles" in data["missing"]
    assert "workflows" in data["missing"]


def test_blueprint_validation_rejects_undeclared_runtime_skill() -> None:
    payload = {
        "id": "bp.invalid.undeclared",
        "name": "Invalid Undeclared Skill",
        "goal": "fail validation",
        "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
        "tasks": [],
        "workflows": [{
            "id": "wf.invalid",
            "name": "invalid",
            "triggers": ["manual"],
            "steps": [{"id": "s1", "kind": "skill", "ref": "skill.echo", "config": {}}],
        }],
        "views": [],
        "required_modules": ["state.get"],
        "required_skills": []
    }
    response = client.post("/blueprints/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert any("undeclared skill" in item for item in data["errors"])


def test_blueprint_validation_rejects_build_only_runtime_skill(tmp_path: Path) -> None:
    skill_control = SkillControlService()
    _register_skill(skill_control, "builder.plan", criticality="C0_build_only")
    validation = BlueprintValidationService(SkillValidationService(skill_control=skill_control))

    blueprint = AppBlueprint(
        id="bp.invalid.build-only",
        name="Invalid Build Only",
        goal="fail validation",
        roles=[{"id": "r1", "name": "agent", "type": "agent"}],
        tasks=[],
        workflows=[{"id": "wf.invalid", "name": "invalid", "triggers": ["manual"], "steps": [{"id": "s1", "kind": "skill", "ref": "builder.plan", "config": {}}]}],
        views=[],
        required_modules=["state.get"],
        required_skills=["builder.plan"],
    )

    result = validation.validate(blueprint)
    assert result["ok"] is False
    assert any("Build-only skill cannot be used in runtime workflow steps" in item for item in result["errors"])


def test_blueprint_validation_rejects_unknown_or_future_from_step_reference() -> None:
    schema_registry = SchemaRegistryService()
    schema_registry.register(
        "schema://skill.map/input",
        {"type": "object", "properties": {"payload": {"type": "object"}}, "required": ["payload"], "additionalProperties": False},
    )
    skill_control = SkillControlService()
    _register_skill(skill_control, "skill.map", input_ref="schema://skill.map/input")
    validation = BlueprintValidationService(SkillValidationService(skill_control=skill_control, schema_registry=schema_registry))

    blueprint = AppBlueprint(
        id="bp.invalid.future-step",
        name="Invalid Future Step",
        goal="fail validation",
        roles=[{"id": "r1", "name": "agent", "type": "agent"}],
        tasks=[],
        workflows=[{
            "id": "wf.invalid",
            "name": "invalid",
            "triggers": ["manual"],
            "steps": [
                {"id": "call", "kind": "skill", "ref": "skill.map", "config": {"inputs": {"payload": {"$from_step": "later", "field": "value"}}}},
                {"id": "later", "kind": "module", "ref": "state.set", "config": {"key": "x", "value": {"ok": True}}},
            ],
        }],
        views=[],
        required_modules=["state.set"],
        required_skills=["skill.map"],
    )

    result = validation.validate(blueprint)
    assert result["ok"] is False
    assert any("unknown or future step" in item for item in result["errors"])


def test_blueprint_validation_rejects_missing_required_input_field() -> None:
    schema_registry = SchemaRegistryService()
    schema_registry.register(
        "schema://skill.map/input",
        {"type": "object", "properties": {"payload": {"type": "object"}, "mode": {"type": "string"}}, "required": ["payload", "mode"], "additionalProperties": False},
    )
    skill_control = SkillControlService()
    _register_skill(skill_control, "skill.map", input_ref="schema://skill.map/input")
    validation = BlueprintValidationService(SkillValidationService(skill_control=skill_control, schema_registry=schema_registry))

    blueprint = AppBlueprint(
        id="bp.invalid.missing-input",
        name="Invalid Missing Input",
        goal="fail validation",
        roles=[{"id": "r1", "name": "agent", "type": "agent"}],
        tasks=[],
        workflows=[{
            "id": "wf.invalid",
            "name": "invalid",
            "triggers": ["manual"],
            "steps": [
                {"id": "call", "kind": "skill", "ref": "skill.map", "config": {"inputs": {"payload": {"value": 1}}}},
            ],
        }],
        views=[],
        required_modules=[],
        required_skills=["skill.map"],
    )

    result = validation.validate(blueprint)
    assert result["ok"] is False
    assert any("missing required input field: mode" in item for item in result["errors"])


def test_blueprint_validation_rejects_incompatible_prior_skill_output_mapping() -> None:
    schema_registry = SchemaRegistryService()
    schema_registry.register(
        "schema://skill.producer/output",
        {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"], "additionalProperties": False},
    )
    schema_registry.register(
        "schema://skill.consumer/input",
        {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
    )
    skill_control = SkillControlService()
    _register_skill(skill_control, "skill.producer", output_ref="schema://skill.producer/output")
    _register_skill(skill_control, "skill.consumer", input_ref="schema://skill.consumer/input")
    validation = BlueprintValidationService(SkillValidationService(skill_control=skill_control, schema_registry=schema_registry))

    blueprint = AppBlueprint(
        id="bp.invalid.output-input-mismatch",
        name="Invalid Output Input Mismatch",
        goal="fail validation",
        roles=[{"id": "r1", "name": "agent", "type": "agent"}],
        tasks=[],
        workflows=[{
            "id": "wf.invalid",
            "name": "invalid",
            "triggers": ["manual"],
            "steps": [
                {"id": "produce", "kind": "skill", "ref": "skill.producer", "config": {}},
                {"id": "consume", "kind": "skill", "ref": "skill.consumer", "config": {"inputs": {"message": {"$from_step": "produce", "field": "count"}}}},
            ],
        }],
        views=[],
        required_modules=[],
        required_skills=["skill.producer", "skill.consumer"],
    )

    result = validation.validate(blueprint)
    assert result["ok"] is False
    assert any("maps incompatible schema" in item for item in result["errors"])


def test_installer_rejects_invalid_blueprint_with_missing_skill(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "blueprint-validation-store"))
    registry = AppRegistryService(store=store)
    lifecycle = AppLifecycleService(store=store)
    runtime = AppRuntimeHostService(lifecycle=lifecycle, store=store)
    data_store = AppDataStore(base_dir=str(tmp_path / "blueprint-validation-ns"), store=store)
    app_config = AppConfigService(data_store=data_store, store=store)
    skill_control = SkillControlService()
    for skill_id in ["system.app_config", "system.context", "system.state", "system.audit"]:
        _register_skill(skill_control, skill_id)
    resolver = AppProfileResolverService(skill_control=skill_control)
    validation = BlueprintValidationService(SkillValidationService(skill_control=skill_control))
    installer = AppInstallerService(
        registry=registry,
        lifecycle=lifecycle,
        runtime_host=runtime,
        data_store=data_store,
        app_config_service=app_config,
        app_profile_resolver=resolver,
        blueprint_validation=validation,
    )

    registry.register_blueprint(
        AppBlueprint(
            id="bp.invalid.missing-skill",
            name="Invalid Missing Skill",
            goal="fail install",
            roles=[{"id": "r1", "name": "agent", "type": "agent"}],
            tasks=[],
            workflows=[{"id": "wf.invalid", "name": "invalid", "triggers": ["manual"], "steps": []}],
            views=[],
            required_modules=["state.get"],
            required_skills=["skill.missing"],
        )
    )

    try:
        installer.install_app("bp.invalid.missing-skill", user_id="user.invalid")
        assert False, "expected installer validation failure"
    except AppInstallerError as error:
        assert "Required skill not found: skill.missing" in str(error)
