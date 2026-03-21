from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_create_script_skill_without_command_returns_structured_diagnostic() -> None:
    response = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.script.missing.command",
            "name": "Broken Script Skill",
            "adapter_kind": "script",
            "schemas": {
                "input": {"type": "object", "properties": {}, "additionalProperties": False},
                "output": {"type": "object", "properties": {}, "additionalProperties": True},
                "error": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
            },
        },
    )

    assert response.status_code == 400
    payload = response.json()["detail"]
    assert payload["stage"] == "create"
    assert payload["kind"] == "invalid_request"
    assert "requires command" in payload["message"].lower()
    assert payload["hint"]


def test_create_callable_skill_with_unknown_generation_operation_returns_structured_diagnostic() -> None:
    response = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.callable.unknown.op",
            "name": "Broken Callable Skill",
            "adapter_kind": "callable",
            "generation_operation": "not_supported_yet",
            "schemas": {
                "input": {"type": "object", "properties": {"payload": {"type": "object"}}, "required": ["payload"], "additionalProperties": False},
                "output": {"type": "object", "properties": {"normalized": {"type": "object"}}, "required": ["normalized"], "additionalProperties": True},
                "error": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False},
            },
            "smoke_test_inputs": {"payload": {"A": 1}},
        },
    )

    assert response.status_code == 400
    payload = response.json()["detail"]
    assert payload["stage"] == "create"
    assert payload["kind"] == "callable_generation_error"
    assert payload["details"]["generation_operation"] == "not_supported_yet"


def test_install_run_contract_failure_returns_structured_execute_diagnostic() -> None:
    create_skill = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.script.diagnostic.slugify",
            "name": "Diagnostic Slugify Skill",
            "adapter_kind": "script",
            "command": ["python3", "tests/fixtures/script_slugify_skill.py"],
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
                        "source_text": {"type": "string"},
                        "slug": {"type": "string"},
                        "length": {"type": "integer"},
                        "adapter": {"type": "string"},
                    },
                    "required": ["source_text", "slug", "length", "adapter"],
                    "additionalProperties": True,
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "smoke_test_inputs": {"text": "ok"},
        },
    )
    assert create_skill.status_code == 200

    response = client.post(
        "/apps/from-skills/install-run",
        json={
            "blueprint_id": "bp.diagnostic.slugify",
            "name": "Diagnostic Slugify App",
            "goal": "trigger contract mismatch diagnostic",
            "skill_ids": ["skill.script.diagnostic.slugify"],
            "workflow_id": "wf.diagnostic.slugify",
            "user_id": "diag-user",
            "step_inputs": {
                "skill.1": {"wrong_field": "boom"}
            },
        },
    )

    assert response.status_code == 400
    payload = response.json()["detail"]
    assert payload["stage"] in {"install", "execute"}
    assert payload["kind"] in {"install_error", "contract_violation", "execution_error"}
    assert payload["hint"]
    assert payload["suggested_retry_request"]


def test_app_from_skills_rejects_invalid_step_mapping_request() -> None:
    response = client.post(
        "/apps/from-skills",
        json={
            "blueprint_id": "bp.invalid.mapping.request",
            "name": "Invalid Mapping Request",
            "goal": "trigger invalid mapping diagnostic",
            "skill_ids": ["system.context"],
            "workflow_id": "wf.invalid.mapping.request",
            "step_mappings": {
                "skill.1": [
                    {"target_field": "payload.value"}
                ]
            },
        },
    )

    assert response.status_code == 400
    payload = response.json()["detail"]
    assert "requires from_step or from_inputs" in payload.lower()


def test_diagnose_retry_returns_suggested_request() -> None:
    response = client.post(
        "/skills/diagnose-retry",
        json={
            "diagnostic": {
                "stage": "create",
                "kind": "invalid_request",
                "message": "Script skill creation requires command",
                "retryable": False,
                "hint": "Provide a script command list for script-backed skills.",
                "details": {
                    "skill_id": "skill.script.retry.example",
                    "adapter_kind": "script"
                },
                "suggested_retry_request": {
                    "skill_id": "skill.script.retry.example",
                    "adapter_kind": "script",
                    "command": ["python3", "path/to/generated_skill.py"]
                }
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["retryable"] is True
    assert payload["suggested_request"]["skill_id"] == "skill.script.retry.example"
    assert payload["suggested_request"]["command"][0] == "python3"
