from fastapi.testclient import TestClient

from app.api.main import app, policy_authority

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


def test_phase5_refinement_closure_reports_install_failure_as_diagnostic() -> None:
    blueprint_response = client.post(
        "/skill-blueprints",
        json={
            "skill_id": "skill.phase5.install.fail",
            "name": "Phase5 Install Fail",
            "goal": "trigger install diagnostic",
            "inputs": ["payload"],
            "outputs": ["result"],
            "steps": ["normalize keys", "return normalized object"],
            "related_experience_ids": ["exp.phase5.3"],
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
            "blueprint_id": "bp.phase5.install.fail",
            "name": "Phase5 Install Fail App",
            "goal": "assemble and install candidate from suggested skills",
            "skill_ids": ["skill.phase5.install.fail"],
            "workflow_id": "wf.phase5.install.fail",
            "persist_missing_skills": True,
            "install": True,
            "run": False,
            "user_id": "",
            "reviewer": "phase5-reviewer",
            "version": "candidate-1",
            "note": "phase5 install diagnostic"
        },
    )
    assert closure_response.status_code == 200
    payload = closure_response.json()
    assert payload["release_entry"] is not None
    assert payload["compare_summary"]["blueprint_id"] == "bp.phase5.install.fail"
    assert payload["install_result"] is None
    assert payload["execution_result"] is None
    assert len(payload["diagnostics"]) == 1
    assert payload["diagnostics"][0]["stage"] == "install"
    assert payload["diagnostics"][0]["kind"] == "install_error"
    assert payload["diagnostics"][0]["retryable"] is False


def test_phase5_refinement_closure_reports_policy_block_as_diagnostic() -> None:
    previous = policy_authority.get_policy("generated_app_assembly")
    policy_authority.set_policy(
        previous.model_copy(update={
            "require_reviewer": True,
            "allowed_reviewers": ["ops-reviewer"],
            "require_reason": True,
            "allow_automatic": False,
        })
    )
    try:
        closure_response = client.post(
            "/apps/refine-from-suggested-skills/closure",
            json={
                "blueprint_id": "bp.phase5.policy.blocked",
                "name": "Phase5 Policy Blocked App",
                "goal": "blocked by authority before refinement",
                "skill_ids": ["skill.phase5.normalize"],
                "workflow_id": "wf.phase5.policy.blocked",
                "persist_missing_skills": True,
                "install": False,
                "run": False,
                "reviewer": "unauthorized-reviewer",
                "version": "candidate-1",
                "note": "phase5 policy blocked"
            },
        )
        assert closure_response.status_code == 200
        payload = closure_response.json()
        assert payload["blueprint"] is None
        assert payload["app_result"] is None
        assert payload["compare_summary"]["blueprint_id"] == "bp.phase5.policy.blocked"
        assert len(payload["diagnostics"]) == 1
        diagnostic = payload["diagnostics"][0]
        assert diagnostic["stage"] == "assemble"
        assert diagnostic["kind"] == "policy_blocked"
        assert diagnostic["retryable"] is False
        assert diagnostic["details"]["scope"] == "generated_app_assembly"
    finally:
        policy_authority.set_policy(previous)
