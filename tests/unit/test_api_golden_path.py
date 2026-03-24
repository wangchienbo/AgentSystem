from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_api_golden_path_flow_from_registry_to_dashboard() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.api.golden.path",
            "name": "API Golden Path App",
            "goal": "exercise api golden path",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.api.golden",
                    "name": "api golden",
                    "triggers": ["manual"],
                    "steps": [
                        {
                            "id": "set.input",
                            "kind": "module",
                            "ref": "state.set",
                            "config": {
                                "key": "api.golden.input",
                                "value": {"token": {"$from_inputs": "token", "default": "missing"}},
                            },
                        },
                        {"id": "blocked.skill", "kind": "skill", "ref": "skill.blocked", "config": {"mode": "fail"}},
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
        "/registry/apps/bp.api.golden.path/install",
        json={"user_id": "api-golden-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.api.golden", "trigger": "api", "inputs": {"token": "api-golden-token"}},
    )
    assert execute_response.status_code == 200
    execution = execute_response.json()
    assert execution["status"] == "partial"
    assert execution["failed_step_ids"] == ["blocked.skill"]
    assert execution["outputs"]["inputs"]["token"] == "api-golden-token"

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200
    retried = retry_response.json()
    assert retried["trigger"] == "retry:api"
    assert retried["retry_comparison"]["previous_failed_step_ids"] == ["blocked.skill"]
    assert retried["retry_comparison"]["unchanged_failed_step_ids"] == ["blocked.skill"]

    diagnostics_response = client.get(
        "/workflows/diagnostics",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.api.golden",
            "failed_step_id": "blocked.skill",
        },
    )
    assert diagnostics_response.status_code == 200
    diagnostics = diagnostics_response.json()
    assert diagnostics["latest_execution"] is not None
    assert diagnostics["latest_failure"] is not None
    assert diagnostics["latest_retry"] is not None

    overview_response = client.get(
        "/workflows/overview",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.api.golden",
            "failed_step_id": "blocked.skill",
        },
    )
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["health"]["health_status"] == "failing"
    assert overview["health"]["unresolved_failure_count"] == 1

    dashboard_response = client.get(
        "/workflows/dashboard",
        params={
            "app_instance_id": app_instance_id,
            "workflow_id": "wf.api.golden",
            "failed_step_id": "blocked.skill",
            "timeline_limit": 2,
        },
    )
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["stats"]["total_executions"] >= 2
    assert dashboard["stats"]["total_failures"] >= 1
    assert dashboard["stats"]["total_retries"] >= 1
    assert dashboard["recent_timeline"]["meta"]["returned_count"] >= 1
    assert len(dashboard["recent_timeline"]["items"]) >= 1
