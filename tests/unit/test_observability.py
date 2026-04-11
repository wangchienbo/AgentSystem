from pathlib import Path

from tests.unit.api_test_helper import create_isolated_test_client



def test_retry_last_failed_workflow_api_flow(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.retry.api",
            "name": "Retry API App",
            "goal": "retry failed workflows",
            "roles": [],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.retry",
                    "name": "retry",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "step.blocked", "kind": "skill", "ref": "skill.not.allowed", "config": {}},
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
        "/registry/apps/bp.retry.api/install",
        json={"user_id": "retry-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.retry", "trigger": "api", "inputs": {"token": "retry-me"}},
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["status"] == "blocked_by_policy"
    assert execute_response.json()["failed_step_ids"] == ["step.blocked"]

    retry_response = client.post(f"/apps/{app_instance_id}/workflows/retry-last-failure")
    assert retry_response.status_code == 200
    assert retry_response.json()["workflow_id"] == "wf.retry"
    assert retry_response.json()["trigger"].startswith("retry:")
    assert retry_response.json()["outputs"]["inputs"]["token"] == "retry-me"
    assert retry_response.json()["status"] == "blocked_by_policy"


def test_workflow_and_skill_observability_api_flow(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.observability.api",
            "name": "Observability API App",
            "goal": "inspect workflow and skill execution history",
            "roles": [],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.observe",
                    "name": "observe",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "step.ok", "kind": "skill", "ref": "skill.echo", "config": {"payload": {"msg": "ok"}}},
                        {"id": "step.blocked", "kind": "skill", "ref": "skill.not.allowed", "config": {}},
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
        "/registry/apps/bp.observability.api/install",
        json={"user_id": "observability-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.observe", "trigger": "api"},
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["status"] == "blocked_by_policy"
    assert execute_response.json()["failed_step_ids"] == ["step.blocked"]

    history_response = client.get("/workflows/history", params={"app_instance_id": app_instance_id})
    assert history_response.status_code == 200
    assert len(history_response.json()) >= 1
    assert history_response.json()[-1]["workflow_id"] == "wf.observe"

    failures_response = client.get("/workflows/failures", params={"app_instance_id": app_instance_id})
    assert failures_response.status_code == 200
    assert len(failures_response.json()) >= 1
    assert failures_response.json()[-1]["status"] == "blocked_by_policy"
    assert failures_response.json()[-1]["failed_step_ids"] == ["step.blocked"]

    skill_failures_response = client.get("/skill-runtime/failures")
    assert skill_failures_response.status_code == 200
    assert isinstance(skill_failures_response.json(), list)
