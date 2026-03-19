from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_context_policy_and_auto_compaction_flow() -> None:
    install_response = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "context-policy-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    policy_response = client.post(
        f"/app-contexts/{app_instance_id}/policy",
        json={"max_context_entries": 1, "compact_on_workflow_complete": True},
    )
    assert policy_response.status_code == 200
    assert policy_response.json()["max_context_entries"] == 1

    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "open_loops", "key": "policy-trigger", "value": {"pending": True}},
    )
    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"trigger": "api", "inputs": {"topic": "policy"}},
    )
    assert execute_response.status_code == 200

    layers_response = client.get(f"/app-contexts/{app_instance_id}/layers")
    assert layers_response.status_code == 200
    assert layers_response.json()["layers"]["summary"] is not None


def test_context_policy_compacts_on_stage_change_and_persists_runtime_snapshot() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.context.stage.change",
            "name": "Context Stage Change App",
            "goal": "exercise stage-change compaction",
            "roles": [],
            "tasks": [],
            "workflows": [
                {"id": "wf.alpha", "name": "alpha", "triggers": ["manual"], "steps": []},
                {"id": "wf.beta", "name": "beta", "triggers": ["manual"], "steps": []},
            ],
            "views": [],
            "required_modules": [],
            "required_skills": [],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive"
            }
        },
    )
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.context.stage.change/install",
        json={"user_id": "context-stage-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    policy_response = client.post(
        f"/app-contexts/{app_instance_id}/policy",
        json={"compact_on_workflow_complete": False, "compact_on_workflow_failure": False, "compact_on_stage_change": True},
    )
    assert policy_response.status_code == 200
    assert policy_response.json()["compact_on_stage_change"] is True

    first_execute = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.alpha", "trigger": "api", "inputs": {"topic": "alpha"}},
    )
    assert first_execute.status_code == 200

    second_execute = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.beta", "trigger": "api", "inputs": {"topic": "beta"}},
    )
    assert second_execute.status_code == 200

    layers_response = client.get(f"/app-contexts/{app_instance_id}/layers")
    assert layers_response.status_code == 200
    assert layers_response.json()["layers"]["summary"] is not None
    assert layers_response.json()["layers"]["summary"]["metadata"]["compact_reason"] == "stage_change"

    persistence_response = client.get("/runtime/persistence")
    assert persistence_response.status_code == 200
    assert app_instance_id in persistence_response.json()["context_summaries"]
    assert app_instance_id in persistence_response.json()["context_policies"]


def test_skill_execution_receives_working_set() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.skill.working-set",
            "name": "Skill Working Set App",
            "goal": "inject working set into skill inputs",
            "roles": [],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.skill.working-set",
                    "name": "skill working set",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "echo", "kind": "skill", "ref": "skill.echo", "config": {"payload": {"msg": "hi"}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": [],
            "required_skills": ["skill.echo"],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive"
            }
        },
    )
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.skill.working-set/install",
        json={"user_id": "working-set-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "decisions", "key": "be-brief", "value": {"enabled": True}},
    )
    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.skill.working-set", "trigger": "api", "inputs": {"source": "test"}},
    )
    assert execute_response.status_code == 200
    assert "echo" in execute_response.json()["steps"][0]["output"]
    working_set_response = client.get(f"/app-contexts/{app_instance_id}/working-set")
    assert working_set_response.status_code == 200
    assert working_set_response.json()["layer"] == "working_set"
    assert "be-brief" in working_set_response.json()["decisions"]
    assert working_set_response.json()["metadata"]["skill_execution_count"] >= 1

    layers_response = client.get(f"/app-contexts/{app_instance_id}/layers")
    assert layers_response.status_code == 200
    assert layers_response.json()["layers"]["detail"]["skill_execution_count"] >= 1
