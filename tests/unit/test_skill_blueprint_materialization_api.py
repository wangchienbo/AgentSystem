from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_materialize_low_risk_blueprint_blocks_shell_script_materialization() -> None:
    add_blueprint = client.post(
        "/skill-blueprints",
        json={
            "skill_id": "skill.blueprint.blocked.shell",
            "name": "Blocked Shell Blueprint",
            "goal": "should not allow shell materialization under safe defaults",
            "inputs": ["payload"],
            "outputs": ["normalized"],
            "steps": ["keep execution local and deterministic"],
            "related_experience_ids": ["exp.materialize.blocked"],
            "safety_profile": {
                "preferred_risk_level": "R0_safe_read",
                "prefer_local_only": True,
                "prefer_deterministic": True,
                "allow_network": False,
                "allow_shell": False,
                "allow_filesystem_write": False
            }
        },
    )
    assert add_blueprint.status_code == 200

    blocked = client.post(
        "/skill-blueprints/skill.blueprint.blocked.shell/materialize",
        json={
            "adapter_kind": "script",
            "command": ["bash", "tests/fixtures/script_echo_skill.py"],
            "schemas": {
                "input": {"type": "object", "properties": {}, "additionalProperties": True},
                "output": {"type": "object", "properties": {}, "additionalProperties": True},
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False
                }
            }
        },
    )
    assert blocked.status_code == 400
    payload = blocked.json()["detail"]
    assert payload["stage"] == "materialize"
    assert payload["kind"] == "policy_blocked"
    assert "blueprint.allow_shell=false" in payload["details"]["policy_reasons"]



def test_materialize_skill_blueprint_uses_safety_defaults_in_creation_request() -> None:
    add_blueprint = client.post(
        "/skill-blueprints",
        json={
            "skill_id": "skill.blueprint.materialized",
            "name": "Materialized Safe Blueprint",
            "goal": "materialize a blueprint into a real skill",
            "inputs": ["payload"],
            "outputs": ["normalized"],
            "steps": ["normalize safe payload locally"],
            "related_experience_ids": ["exp.materialize.1"],
            "safety_profile": {
                "preferred_risk_level": "R0_safe_read",
                "prefer_local_only": True,
                "prefer_deterministic": True,
                "allow_network": False,
                "allow_shell": False,
                "allow_filesystem_write": False
            }
        },
    )
    assert add_blueprint.status_code == 200

    materialize = client.post(
        "/skill-blueprints/skill.blueprint.materialized/materialize",
        json={
            "adapter_kind": "callable",
            "generation_operation": "normalize_object_keys",
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"payload": {"type": "object"}},
                    "required": ["payload"],
                    "additionalProperties": False
                },
                "output": {
                    "type": "object",
                    "properties": {"normalized": {"type": "object"}, "adapter": {"type": "string"}},
                    "required": ["normalized", "adapter"],
                    "additionalProperties": True
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False
                }
            },
            "smoke_test_inputs": {"payload": {"Display Name": "Agent System"}}
        },
    )
    assert materialize.status_code == 200
    payload = materialize.json()
    creation_request = payload["creation_request"]
    creation_result = payload["creation_result"]
    registered_skill = payload["registered_skill"]

    assert creation_request["capability_profile"]["risk_level"] == "R0_safe_read"
    assert creation_request["capability_profile"]["network_requirement"] == "N0_none"
    assert creation_request["capability_profile"]["execution_locality"] == "local"
    assert creation_result["created"] is True
    assert creation_result["registered"] is True
    assert registered_skill["capability_profile"]["risk_level"] == "R0_safe_read"
    assert registered_skill["capability_profile"]["network_requirement"] == "N0_none"
    assert registered_skill["capability_profile"]["execution_locality"] == "local"
    assert registered_skill["manifest"]["risk"]["risk_level"] == "R0_safe_read"
    assert registered_skill["manifest"]["risk"]["allow_network"] is False
    assert registered_skill["manifest"]["risk"]["allow_shell"] is False
