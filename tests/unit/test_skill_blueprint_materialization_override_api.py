from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def _ensure_blueprint() -> None:
    client.post(
        "/skill-blueprints",
        json={
            "skill_id": "skill.blueprint.override.shell",
            "name": "Override Shell Blueprint",
            "goal": "allow shell materialization only through explicit override",
            "inputs": ["payload"],
            "outputs": ["normalized"],
            "steps": ["default to safe local execution"],
            "related_experience_ids": ["exp.materialize.override"],
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


def test_blueprint_materialization_can_be_unblocked_by_materialization_scope_override() -> None:
    _ensure_blueprint()
    client.post(
        "/skill-risk/skill.blueprint.override.shell/revoke",
        params={"reviewer": "setup", "reason": "reset test state", "scope": "blueprint_materialization"},
    )

    blocked = client.post(
        "/skill-blueprints/skill.blueprint.override.shell/materialize",
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
    assert blocked.json()["detail"]["kind"] == "policy_blocked"
    assert blocked.json()["detail"]["details"]["override_scope"] == "blueprint_materialization"

    approved = client.post(
        "/skill-risk/skill.blueprint.override.shell/approve",
        params={
            "reviewer": "tester",
            "reason": "allow shell materialization for controlled test",
            "scope": "blueprint_materialization",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["scope"] == "blueprint_materialization"

    allowed = client.post(
        "/skill-blueprints/skill.blueprint.override.shell/materialize",
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
    assert allowed.status_code == 200
    assert allowed.json()["creation_result"]["created"] is True
