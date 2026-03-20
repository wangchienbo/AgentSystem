from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_create_script_skill_via_api_and_smoke_execute() -> None:
    response = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.script.generated",
            "name": "Generated Script Skill",
            "description": "generated through api",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_echo_skill.py"],
            "tags": ["generated", "script"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "echo": {"type": "string"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["echo", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "hello-generated"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["skill_id"] == "skill.script.generated"
    assert payload["runtime_adapter"] == "script"
    assert payload["smoke_test"]["status"] == "completed"
    assert payload["smoke_test"]["output"]["echo"] == "hello-generated"

    list_response = client.get("/skills")
    assert list_response.status_code == 200
    assert any(item["skill_id"] == "skill.script.generated" for item in list_response.json())


def test_create_app_blueprint_from_generated_skills_via_api() -> None:
    create_skill = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.script.for.app",
            "name": "Generated Script App Skill",
            "description": "used by generated app blueprint",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_echo_skill.py"],
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "echo": {"type": "string"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["echo", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "app-skill"},
        },
    )
    assert create_skill.status_code == 200

    response = client.post(
        "/apps/from-skills",
        json={
            "blueprint_id": "bp.generated.skill.app",
            "name": "Generated Skill App",
            "goal": "assemble an app from generated skills",
            "skill_ids": ["skill.script.for.app"],
            "workflow_id": "wf.generated.skill.app",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["blueprint"]["id"] == "bp.generated.skill.app"
    assert payload["result"]["required_skills"] == ["skill.script.for.app"]
    assert payload["result"]["created_steps"] == ["skill.1"]

    blueprints = client.get("/registry/apps")
    assert blueprints.status_code == 200
    assert any(item["blueprint_id"] == "bp.generated.skill.app" for item in blueprints.json())
