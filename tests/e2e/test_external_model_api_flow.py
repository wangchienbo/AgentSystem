from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_external_model_api_flow_via_skill_runtime() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.external.model.probe",
            "name": "External Model Probe App",
            "goal": "verify external model API connectivity through skill runtime",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.external.model.probe",
                    "name": "external model probe",
                    "triggers": ["manual"],
                    "steps": [
                        {"id": "probe", "kind": "skill", "ref": "model.responses.probe", "config": {"inputs": {"prompt": "Return only MODEL_PROBE_OK"}}},
                    ],
                }
            ],
            "views": [],
            "required_modules": [],
            "required_skills": ["model.responses.probe"],
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
        "/registry/apps/bp.external.model.probe/install",
        json={"user_id": "external-model-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"workflow_id": "wf.external.model.probe", "trigger": "api", "inputs": {}},
    )
    assert execute_response.status_code == 200
    execution = execute_response.json()
    assert execution["status"] == "completed"
    output = execution["steps"][0]["output"]
    assert output["provider"] == "OpenAICompatible"
    assert output["model"] == "gpt-5.4"
    assert isinstance(output["result"], dict)

    executions_response = client.get("/skill-runtime/executions")
    assert executions_response.status_code == 200
    assert any(item["skill_id"] == "model.responses.probe" for item in executions_response.json())
