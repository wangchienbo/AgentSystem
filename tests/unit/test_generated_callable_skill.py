from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.skill_creation import SkillCreationRequest, SkillSchemaDefinition
from app.models.skill_runtime import SkillExecutionRequest
from app.services.app_data_store import AppDataStore
from app.services.generated_callable_materializer import GeneratedCallableMaterializer
from app.services.generated_skill_assets import GeneratedSkillAssetStore
from app.services.runtime_state_store import RuntimeStateStore
from app.services.schema_registry import SchemaRegistryService
from app.services.skill_control import SkillControlService
from app.services.skill_factory import SkillFactoryService
from app.services.skill_runtime import SkillRuntimeService


client = TestClient(app)


def test_create_real_callable_skill_via_api_and_install_run() -> None:
    create_response = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.object.normalize_keys",
            "name": "Normalize Object Keys",
            "description": "normalize object keys into stable snake_case-like keys",
            "adapter_kind": "callable",
            "generation_operation": "normalize_object_keys",
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"payload": {"type": "object"}},
                    "required": ["payload"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "normalized": {"type": "object"},
                        "top_level_keys": {"type": "array", "items": {"type": "string"}},
                        "adapter": {"type": "string"},
                    },
                    "required": ["normalized", "top_level_keys", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {
                "payload": {
                    "Display Name": "Agent System",
                    "User-ID": 7,
                    "Nested Value": {"Inner Key": True},
                }
            },
        },
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["runtime_adapter"] == "callable"
    assert create_payload["smoke_test"]["status"] == "completed"
    assert create_payload["smoke_test"]["output"]["normalized"]["display_name"] == "Agent System"
    assert create_payload["smoke_test"]["output"]["normalized"]["nested_value"]["inner_key"] is True

    run_response = client.post(
        "/apps/from-skills/install-run",
        json={
            "blueprint_id": "bp.object.normalize_keys",
            "name": "Normalize Keys App",
            "goal": "normalize integration payload keys before later use",
            "skill_ids": ["skill.object.normalize_keys"],
            "workflow_id": "wf.object.normalize_keys",
            "user_id": "callable-user",
            "step_inputs": {
                "skill.1": {
                    "payload": {
                        "Project Name": "App OS",
                        "Owner Email": "owner@example.com",
                    }
                }
            },
        },
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["execution"]["status"] == "completed"
    assert run_payload["execution"]["steps"][0]["output"]["normalized"]["project_name"] == "App OS"
    assert run_payload["execution"]["steps"][0]["output"]["adapter"] == "callable"


def test_create_real_callable_validation_skill_via_api_and_install_run() -> None:
    create_response = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.object.validate_required_fields",
            "name": "Validate Required Fields",
            "description": "validate required fields in a structured payload deterministically",
            "adapter_kind": "callable",
            "generation_operation": "validate_required_fields",
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {
                        "payload": {"type": "object"},
                        "required_fields": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["payload", "required_fields"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "valid": {"type": "boolean"},
                        "missing_fields": {"type": "array", "items": {"type": "string"}},
                        "checked_fields": {"type": "array", "items": {"type": "string"}},
                        "adapter": {"type": "string"}
                    },
                    "required": ["valid", "missing_fields", "checked_fields", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {
                "payload": {"title": "Agent System", "owner": "bo"},
                "required_fields": ["title", "owner", "status"],
            },
        },
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["runtime_adapter"] == "callable"
    assert create_payload["smoke_test"]["status"] == "completed"
    assert create_payload["smoke_test"]["output"]["valid"] is False
    assert create_payload["smoke_test"]["output"]["missing_fields"] == ["status"]

    run_response = client.post(
        "/apps/from-skills/install-run",
        json={
            "blueprint_id": "bp.object.validate_required_fields",
            "name": "Validate Required Fields App",
            "goal": "validate structured payload completeness before processing",
            "skill_ids": ["skill.object.validate_required_fields"],
            "workflow_id": "wf.object.validate_required_fields",
            "user_id": "validation-user",
            "step_inputs": {
                "skill.1": {
                    "payload": {"title": "Agent System", "owner": "bo", "status": "active"},
                    "required_fields": ["title", "owner", "status"],
                }
            },
        },
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["execution"]["status"] == "completed"
    assert run_payload["execution"]["steps"][0]["output"]["valid"] is True
    assert run_payload["execution"]["steps"][0]["output"]["missing_fields"] == []
    assert run_payload["execution"]["steps"][0]["output"]["adapter"] == "callable"


def test_generated_callable_skill_persists_and_reloads(tmp_path: Path) -> None:
    runtime_store = RuntimeStateStore(base_dir=str(tmp_path / "runtime-store"))
    data_store = AppDataStore(base_dir=str(tmp_path / "namespaces"), store=runtime_store)
    schema_registry = SchemaRegistryService()
    skill_control = SkillControlService()
    skill_runtime = SkillRuntimeService(store=runtime_store, schema_registry=schema_registry)
    generated_assets = GeneratedSkillAssetStore(data_store)
    materializer = GeneratedCallableMaterializer(base_dir=str(tmp_path / "generated-callables"))
    factory = SkillFactoryService(
        skill_control=skill_control,
        skill_runtime=skill_runtime,
        schema_registry=schema_registry,
        generated_assets=generated_assets,
        callable_materializer=materializer,
    )

    request = SkillCreationRequest(
        skill_id="skill.object.normalize_keys.persisted",
        name="Persisted Normalize Object Keys",
        description="persisted callable generated skill",
        adapter_kind="callable",
        generation_operation="normalize_object_keys",
        schemas=SkillSchemaDefinition(
            input={
                "type": "object",
                "properties": {"payload": {"type": "object"}},
                "required": ["payload"],
                "additionalProperties": False,
            },
            output={
                "type": "object",
                "properties": {
                    "normalized": {"type": "object"},
                    "top_level_keys": {"type": "array", "items": {"type": "string"}},
                    "adapter": {"type": "string"},
                },
                "required": ["normalized", "top_level_keys", "adapter"],
                "additionalProperties": True,
            },
            error={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            },
        ),
        smoke_test_inputs={"payload": {"Hello World": 1, "Nested Key": {"Inner Value": 2}}},
    )

    created = factory.create_skill(request)
    assert created.smoke_test.status == "completed"
    assert created.smoke_test.output["normalized"]["hello_world"] == 1

    reloaded_schema_registry = SchemaRegistryService()
    reloaded_skill_control = SkillControlService()
    reloaded_skill_runtime = SkillRuntimeService(store=runtime_store, schema_registry=reloaded_schema_registry)
    reloaded_assets = GeneratedSkillAssetStore(data_store)
    reloaded_factory = SkillFactoryService(
        skill_control=reloaded_skill_control,
        skill_runtime=reloaded_skill_runtime,
        schema_registry=reloaded_schema_registry,
        generated_assets=reloaded_assets,
        callable_materializer=materializer,
    )

    restored = reloaded_factory.reload_generated_skills()
    assert restored == 1

    result = reloaded_skill_runtime.execute(
        SkillExecutionRequest(
            skill_id="skill.object.normalize_keys.persisted",
            app_instance_id="persisted-app",
            workflow_id="wf.persisted.callable",
            step_id="normalize",
            inputs={"payload": {"Another Key": "ok", "Deep Node": {"Inner Name": "x"}}},
            config={},
        )
    )

    assert result.status == "completed"
    assert result.output["normalized"]["another_key"] == "ok"
    assert result.output["normalized"]["deep_node"]["inner_name"] == "x"
