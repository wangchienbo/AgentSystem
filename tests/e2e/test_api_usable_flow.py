from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_api_usable_flow_for_context_and_config_runtime() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.usable.alpha",
            "name": "Usable Alpha App",
            "goal": "exercise a realistic API-first usable flow",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.usable.alpha",
                    "name": "usable alpha",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "cfg.set", "kind": "skill", "ref": "system.app_config", "config": {"inputs": {"operation": "set", "key": "ui", "value": {"theme": "dark", "density": "compact"}}}},
                        {"id": "ctx.update", "kind": "skill", "ref": "system.context", "config": {"inputs": {"operation": "update", "current_goal": "execute usable alpha flow", "current_stage": "reasoning"}}},
                        {"id": "ctx.append", "kind": "skill", "ref": "system.context", "config": {"inputs": {"operation": "append", "section": "facts", "key": "alpha.fact", "value": {"summary": "api flow executed"}, "tags": ["alpha", "e2e"]}}},
                        {"id": "cfg.get", "kind": "skill", "ref": "system.app_config", "config": {"inputs": {"operation": "get", "key": "ui"}}},
                        {"id": "ctx.get", "kind": "skill", "ref": "system.context", "config": {"inputs": {"operation": "get"}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": [],
            "required_skills": ["system.app_config", "system.context"],
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
        "/registry/apps/bp.usable.alpha/install",
        json={"user_id": "usable-alpha-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    context_response = client.post(
        f"/app-contexts/{app_instance_id}",
        json={"current_goal": "prepare usable alpha", "current_stage": "planning"},
    )
    assert context_response.status_code == 200
    assert context_response.json()["current_stage"] == "planning"

    policy_response = client.post(
        f"/app-contexts/{app_instance_id}/policy",
        json={"max_context_entries": 2, "compact_on_workflow_complete": True},
    )
    assert policy_response.status_code == 200
    assert policy_response.json()["max_context_entries"] == 2

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.usable.alpha", "trigger": "api", "inputs": {"source": "e2e"}},
    )
    assert execute_response.status_code == 200
    execution = execute_response.json()
    assert execution["status"] == "completed"
    assert execution["steps"][3]["output"]["value"]["theme"] == "dark"
    assert execution["steps"][4]["output"]["current_goal"] == "execute usable alpha flow"

    app_response = client.get(f"/apps/{app_instance_id}")
    assert app_response.status_code == 200
    assert app_response.json()["id"] == app_instance_id

    runtime_response = client.get(f"/apps/{app_instance_id}/runtime")
    assert runtime_response.status_code == 200
    assert runtime_response.json()["app_instance"]["id"] == app_instance_id

    context_get_response = client.get(f"/app-contexts/{app_instance_id}")
    assert context_get_response.status_code == 200
    assert context_get_response.json()["current_goal"] == "execute usable alpha flow"

    working_set_response = client.get(f"/app-contexts/{app_instance_id}/working-set")
    assert working_set_response.status_code == 200
    assert working_set_response.json()["layer"] == "working_set"

    layers_response = client.get(f"/app-contexts/{app_instance_id}/layers")
    assert layers_response.status_code == 200
    assert layers_response.json()["layers"]["detail"]["skill_execution_count"] >= 1

    executions_response = client.get("/skill-runtime/executions")
    assert executions_response.status_code == 200
    assert any(item["skill_id"] == "system.context" for item in executions_response.json())
    assert any(item["skill_id"] == "system.app_config" for item in executions_response.json())

    history_response = client.get("/workflows/history", params={"app_instance_id": app_instance_id})
    assert history_response.status_code == 200
    assert any(item["workflow_id"] == "wf.usable.alpha" for item in history_response.json())

    persistence_response = client.get("/runtime/persistence")
    assert persistence_response.status_code == 200
    snapshot = persistence_response.json()
    assert app_instance_id in snapshot["app_instances"]
    assert app_instance_id in snapshot["app_contexts"]
    assert app_instance_id in snapshot["context_policies"]


def test_api_usable_flow_rejects_invalid_blueprint_and_runtime_contract() -> None:
    invalid_validation_response = client.post(
        "/blueprints/validate",
        json={
            "id": "bp.invalid.runtime.wiring",
            "name": "Invalid Runtime Wiring",
            "goal": "reject invalid runtime skill wiring",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.invalid",
                    "name": "invalid",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "bad", "kind": "skill", "ref": "system.context", "config": {"inputs": {"operation": "get", "nonexistent": True}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": [],
            "required_skills": ["system.context"],
        },
    )
    assert invalid_validation_response.status_code == 200
    assert invalid_validation_response.json()["ok"] is False

    invalid_install_register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.invalid.install",
            "name": "Invalid Install App",
            "goal": "fail install",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.invalid.install",
                    "name": "invalid install",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "bad", "kind": "skill", "ref": "skill.missing", "config": {}},
                    ],
                }
            ],
            "views": [],
            "required_modules": [],
            "required_skills": ["skill.missing"],
        },
    )
    assert invalid_install_register_response.status_code == 200

    invalid_install_response = client.post(
        "/registry/apps/bp.invalid.install/install",
        json={"user_id": "invalid-user"},
    )
    assert invalid_install_response.status_code in {400, 404}
