from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_workflow_module_permission_enforcement_blocks_undeclared_module() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.policy.module.guard",
            "name": "Policy Module Guard App",
            "goal": "enforce module declaration policy",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.policy.guard",
                    "name": "policy guard",
                    "triggers": ["manual"],
                    "steps": [
                        {
                            "id": "blocked.module",
                            "kind": "module",
                            "ref": "state.set",
                            "config": {"key": "guarded.key", "value": {"ok": True}},
                        }
                    ],
                }
            ],
            "views": [],
            "required_modules": [],
            "required_skills": [],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive",
            },
        },
    )
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.policy.module.guard/install",
        json={"user_id": "policy-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.policy.guard", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200
    payload = execute_response.json()
    assert payload["status"] == "partial"
    assert payload["failed_step_ids"] == ["blocked.module"]
    assert payload["steps"][0]["detail"]["policy_blocked"] is True
    assert "module not declared in blueprint" in payload["steps"][0]["detail"]["reason"]

    contexts = client.get(f"/app-contexts/{app_instance_id}").json()
    constraint_entries = [item for item in contexts["entries"] if item["section"] == "constraints"]
    assert any("module not declared in blueprint" in str(item["value"].get("reason", "")) for item in constraint_entries)


def test_workflow_event_permission_enforcement_blocks_undeclared_event_when_event_publish_is_enabled() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.policy.event.guard",
            "name": "Policy Event Guard App",
            "goal": "enforce event declaration policy",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.policy.event.guard",
                    "name": "policy event guard",
                    "triggers": ["manual"],
                    "steps": [
                        {
                            "id": "blocked.event",
                            "kind": "event",
                            "ref": "event.secret.publish",
                            "config": {"event_name": "event.secret.publish", "payload": {"ok": True}},
                        }
                    ],
                }
            ],
            "views": [],
            "required_modules": ["event.publish"],
            "required_skills": [],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive",
            },
        },
    )
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.policy.event.guard/install",
        json={"user_id": "policy-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.policy.event.guard", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200
    payload = execute_response.json()
    assert payload["status"] == "partial"
    assert payload["failed_step_ids"] == ["blocked.event"]
    assert payload["steps"][0]["detail"]["policy_blocked"] is True
    assert "event not permitted by blueprint policy" in payload["steps"][0]["detail"]["reason"]


def test_workflow_module_permission_enforcement_allows_declared_module() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.policy.module.allow",
            "name": "Policy Module Allow App",
            "goal": "allow declared module",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.policy.allow",
                    "name": "policy allow",
                    "triggers": ["manual"],
                    "steps": [
                        {
                            "id": "allowed.module",
                            "kind": "module",
                            "ref": "state.set",
                            "config": {"key": "allowed.key", "value": {"ok": True}},
                        }
                    ],
                }
            ],
            "views": [],
            "required_modules": ["state.set"],
            "required_skills": [],
            "runtime_policy": {
                "execution_mode": "service",
                "activation": "on_demand",
                "restart_policy": "on_failure",
                "persistence_level": "full",
                "idle_strategy": "keep_alive",
            },
        },
    )
    assert register_response.status_code == 200

    install_response = client.post(
        "/registry/apps/bp.policy.module.allow/install",
        json={"user_id": "policy-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.policy.allow", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200
    payload = execute_response.json()
    assert payload["status"] == "completed"
    assert payload["failed_step_ids"] == []
    assert payload["steps"][0]["status"] == "completed"
