from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest, SkillManifestRisk
from app.models.skill_adapter import SkillAdapterSpec


client = TestClient(app)


def test_generated_app_assembly_returns_structured_policy_blocked_diagnostic() -> None:
    from app.api.main import skill_control

    skill_control.register(
        SkillRegistryEntry(
            skill_id="skill.policy.blocked.api",
            name="skill.policy.blocked.api",
            active_version="1.0.0",
            versions=[SkillVersion(version="1.0.0", content="ok")],
            dependencies=[],
            capability_profile=SkillCapabilityProfile(risk_level="R4_networked"),
            runtime_adapter="script",
            manifest=SkillManifest(
                skill_id="skill.policy.blocked.api",
                name="skill.policy.blocked.api",
                version="1.0.0",
                description="blocked by policy",
                runtime_adapter="script",
                adapter=SkillAdapterSpec(kind="script", command=["python3", "tests/fixtures/script_echo_skill.py"]),
                contract=SkillContractRef(input_schema_ref="", output_schema_ref="", error_schema_ref=""),
                tags=["generated"],
                risk=SkillManifestRisk(risk_level="R4_networked", allow_network=True),
            ),
        )
    )

    response = client.post(
        "/apps/from-skills",
        json={
            "blueprint_id": "bp.policy.blocked.api",
            "name": "Blocked By Policy",
            "goal": "verify structured policy diagnostics",
            "skill_ids": ["skill.policy.blocked.api"],
            "workflow_id": "wf.policy.blocked.api",
        },
    )

    assert response.status_code == 400
    payload = response.json()["detail"]
    assert payload["stage"] == "assemble"
    assert payload["kind"] == "policy_blocked"
    assert payload["details"]["skill_id"] == "skill.policy.blocked.api"
    assert "allow_network=true" in payload["details"]["policy_reasons"]
    assert payload["hint"]
