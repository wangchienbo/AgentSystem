from fastapi.testclient import TestClient

from app.api.main import app, skill_control
from app.models.skill_adapter import SkillAdapterSpec
from app.models.skill_control import SkillCapabilityProfile, SkillRegistryEntry, SkillVersion
from app.models.skill_manifest import SkillContractRef, SkillManifest, SkillManifestRisk
from app.services.skill_control import SkillControlError


client = TestClient(app)


def _register_blocked_skill() -> None:
    try:
        skill_control.get_skill("skill.override.api")
        return
    except SkillControlError:
        pass
    skill_control.register(
        SkillRegistryEntry(
            skill_id="skill.override.api",
            name="skill.override.api",
            active_version="1.0.0",
            versions=[SkillVersion(version="1.0.0", content="ok")],
            dependencies=[],
            capability_profile=SkillCapabilityProfile(risk_level="R4_networked"),
            runtime_adapter="script",
            manifest=SkillManifest(
                skill_id="skill.override.api",
                name="skill.override.api",
                version="1.0.0",
                description="blocked until override",
                runtime_adapter="script",
                adapter=SkillAdapterSpec(kind="script", command=["python3", "tests/fixtures/script_echo_skill.py"]),
                contract=SkillContractRef(input_schema_ref="", output_schema_ref="", error_schema_ref=""),
                tags=["generated"],
                risk=SkillManifestRisk(risk_level="R4_networked", allow_network=True),
            ),
        )
    )


def test_risk_override_allows_generated_app_assembly_after_approval() -> None:
    _register_blocked_skill()
    client.post("/skill-risk/skill.override.api/revoke", params={"reviewer": "setup", "reason": "reset test state"})

    blocked = client.post(
        "/apps/from-skills",
        json={
            "blueprint_id": "bp.override.blocked",
            "name": "Blocked Override App",
            "goal": "should fail before override",
            "skill_ids": ["skill.override.api"],
            "workflow_id": "wf.override.blocked",
        },
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"]["kind"] == "policy_blocked"

    blocked_events = client.get("/skill-risk/events", params={"skill_id": "skill.override.api"})
    assert blocked_events.status_code == 200
    assert any(item["event_type"] == "policy_blocked" for item in blocked_events.json())

    approved = client.post(
        "/skill-risk/skill.override.api/approve",
        params={"reviewer": "tester", "reason": "allow generated assembly for controlled test"},
    )
    assert approved.status_code == 200
    assert approved.json()["decision"] == "approved_override"

    listed = client.get("/skill-risk/decisions")
    assert listed.status_code == 200
    assert any(item["skill_id"] == "skill.override.api" for item in listed.json())

    event_list = client.get("/skill-risk/events", params={"skill_id": "skill.override.api"})
    assert event_list.status_code == 200
    assert any(item["event_type"] == "override_approved" for item in event_list.json())

    allowed = client.post(
        "/apps/from-skills",
        json={
            "blueprint_id": "bp.override.allowed",
            "name": "Allowed Override App",
            "goal": "should pass after override",
            "skill_ids": ["skill.override.api"],
            "workflow_id": "wf.override.allowed",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["blueprint"]["id"] == "bp.override.allowed"

    revoked = client.post(
        "/skill-risk/skill.override.api/revoke",
        params={"reviewer": "tester", "reason": "close override"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["decision"] == "revoked"
