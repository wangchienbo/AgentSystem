from pathlib import Path

from tests.unit.api_test_helper import create_isolated_test_client


def test_list_skills_exposes_builtin_origin(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    response = client.get("/skills")
    assert response.status_code == 200
    system_app_config = next(item for item in response.json() if item["skill_id"] == "system.app_config")
    assert system_app_config["origin"] == "builtin"


def test_create_script_skill_via_api_and_smoke_execute(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
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
    listed = next(item for item in list_response.json() if item["skill_id"] == "skill.script.generated")
    assert listed["origin"] == "generated"

    detail_response = client.get("/skills/skill.script.generated")
    assert detail_response.status_code == 200
    assert detail_response.json()["origin"] == "generated"


def test_revise_generated_skill_via_api_updates_active_version_and_versions(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    create_response = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.callable.revise.target",
            "name": "Revise Target Skill",
            "description": "initial revision target",
            "adapter_kind": "callable",
            "generation_operation": "extract_text_metadata",
            "schemas": {
                "input": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "original_text": {"type": "string"},
                        "slug": {"type": "string"},
                        "word_count": {"type": "integer"},
                        "has_year": {"type": "boolean"},
                        "years": {"type": "array", "items": {"type": "string"}},
                        "adapter": {"type": "string"}
                    },
                    "required": ["original_text", "slug", "word_count", "has_year", "years", "adapter"],
                    "additionalProperties": True
                },
                "error": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False
                }
            },
            "smoke_test_inputs": {"text": "Revision Base 2026"}
        },
    )
    assert create_response.status_code == 200

    revise_response = client.post(
        "/skills/skill.callable.revise.target/revise",
        json={
            "version": "1.1.0",
            "description": "revised metadata extractor",
            "generation_operation": "extract_text_metadata",
            "smoke_test_inputs": {"text": "Revision Updated 2027"},
            "note": "revise generated callable"
        },
    )
    assert revise_response.status_code == 200
    payload = revise_response.json()
    assert payload["version"] == "1.1.0"
    assert payload["previous_version"] == "1.0.0"
    assert payload["active_version"] == "1.1.0"
    assert payload["smoke_test"]["output"]["years"] == ["2027"]

    detail = client.get("/skills/skill.callable.revise.target")
    assert detail.status_code == 200
    assert detail.json()["active_version"] == "1.1.0"

    versions = client.get("/skills/skill.callable.revise.target/versions")
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()] == ["1.0.0", "1.1.0"]
    assert [item["active"] for item in versions.json()] == [False, True]
    assert versions.json()[1]["revision_status"] == "active"
    assert versions.json()[1]["note"] == "revise generated callable"

    compare = client.get(
        "/skills/skill.callable.revise.target/compare",
        params={"from_version": "1.0.0", "to_version": "1.1.0"},
    )
    assert compare.status_code == 200
    compare_payload = compare.json()
    assert compare_payload["active_version"] == "1.1.0"
    assert compare_payload["active_is_from"] is False
    assert compare_payload["active_is_to"] is True
    assert compare_payload["description_changed"] is True
    assert compare_payload["generation_operation_changed"] is False
    assert compare_payload["change_count"] >= 1
    assert compare_payload["summary"].startswith("Changed:")


def test_revise_generated_skill_can_record_draft_governance_metadata(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    create_response = client.post(
        "/skills/create",
        json={
            "skill_id": "skill.compare.governance.target",
            "name": "Governance Target",
            "description": "baseline governance target",
            "adapter_kind": "callable",
            "generation_operation": "extract_text_metadata",
            "schemas": {
                "input": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},