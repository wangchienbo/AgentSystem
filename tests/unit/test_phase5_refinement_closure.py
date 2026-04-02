from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_phase5_refinement_closure_materializes_and_assembles_candidate() -> None:
    blueprint_response = client.post(
        "/skill-blueprints",
        json={
            "skill_id": "skill.phase5.normalize",
            "name": "Phase5 Normalize",
            "goal": "normalize structured payload",
            "inputs": ["payload"],
            "outputs": ["result"],
            "steps": ["normalize keys", "return normalized object"],
            "related_experience_ids": ["exp.phase5.1"],
            "safety_profile": {
                "preferred_risk_level": "R0_safe_read",
                "prefer_deterministic": True,
                "prefer_callable_materialization": True,
                "allow_network": False,
                "allow_shell": False,
                "allow_filesystem_write": False,
            },
        },
    )
    assert blueprint_response.status_code == 200

    closure_response = client.post(
        "/apps/refine-from-suggested-skills/closure",
        json={
            "blueprint_id": "bp.phase5.candidate",
            "name": "Phase5 Candidate App",
            "goal": "assemble candidate from suggested skills",
            "skill_ids": ["skill.phase5.normalize"],
            "workflow_id": "wf.phase5.candidate",
            "persist_missing_skills": True,
            "install": False,
            "run": False,
            "reviewer": "phase5-reviewer",
            "version": "candidate-1",
            "note": "phase5 first candidate"
        },
    )
    assert closure_response.status_code == 200
    payload = closure_response.json()
    assert payload["materialized_skill_ids"] == ["skill.phase5.normalize"]
    assert payload["release_entry"] is not None
    assert payload["compare_summary"]["blueprint_id"] == "bp.phase5.candidate"
    assert payload["compare_summary"]["required_skills"] == ["skill.phase5.normalize"]
    assert payload["diagnostics"] == []


def test_phase5_refinement_closure_installs_and_runs_candidate() -> None:
    blueprint_response = client.post(
        "/skill-blueprints",
        json={
            "skill_id": "skill.phase5.normalize.run",
            "name": "Phase5 Normalize Run",
            "goal": "normalize structured payload for execution",
            "inputs": ["payload"],
            "outputs": ["result"],
            "steps": ["normalize keys", "return normalized object"],
            "related_experience_ids": ["exp.phase5.2"],
            "safety_profile": {
                "preferred_risk_level": "R0_safe_read",
                "prefer_deterministic": True,
                "prefer_callable_materialization": True,
                "allow_network": False,
                "allow_shell": False,
                "allow_filesystem_write": False,
            },
        },
    )
    assert blueprint_response.status_code == 200

    closure_response = client.post(
        "/apps/refine-from-suggested-skills/closure",
        json={
            "blueprint_id": "bp.phase5.candidate.run",
            "name": "Phase5 Candidate Run App",
            "goal": "assemble, install, and run candidate from suggested skills",
            "skill_ids": ["skill.phase5.normalize.run"],
            "workflow_id": "wf.phase5.candidate.run",
            "persist_missing_skills": True,
            "install": True,
            "run": True,
            "user_id": "phase5-user",
            "workflow_inputs": {"payload": {"hello": "world"}},
            "trigger": "api",
            "reviewer": "phase5-reviewer",
            "version": "candidate-1",
            "note": "phase5 executable candidate"
        },
    )
    assert closure_response.status_code == 200
    payload = closure_response.json()
    assert payload["install_result"] is not None
    assert payload["execution_result"] is not None
    assert payload["execution_result"]["workflow_id"] == "wf.phase5.candidate.run"
    assert payload["release_entry"]["candidate_version"] == "candidate-1"
