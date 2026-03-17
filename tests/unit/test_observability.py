from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_workflow_and_skill_observability_api_flow() -> None:
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
    assert execute_response.json()["status"] == "partial"

    history_response = client.get("/workflows/history", params={"app_instance_id": app_instance_id})
    assert history_response.status_code == 200
    assert len(history_response.json()) >= 1
    assert history_response.json()[-1]["workflow_id"] == "wf.observe"

    failures_response = client.get("/workflows/failures", params={"app_instance_id": app_instance_id})
    assert failures_response.status_code == 200
    assert len(failures_response.json()) >= 1
    assert failures_response.json()[-1]["status"] == "partial"

    skill_failures_response = client.get("/skill-runtime/failures")
    assert skill_failures_response.status_code == 200
    assert isinstance(skill_failures_response.json(), list)
