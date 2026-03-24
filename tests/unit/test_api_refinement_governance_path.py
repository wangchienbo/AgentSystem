import os

os.environ.pop("AGENTSYSTEM_ENABLE_MODEL_REFINER", None)
os.environ.setdefault("AGENTSYSTEM_DISABLE_REFINEMENT_GROUPED_REGRESSION", "1")

from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_api_refinement_governance_flow_from_review_to_dashboard() -> None:
    register_response = client.post(
        "/registry/apps",
        json={
            "id": "bp.api.refinement.path",
            "name": "API Refinement Path App",
            "goal": "exercise api refinement governance path",
            "roles": [{"id": "r1", "name": "agent", "type": "agent"}],
            "tasks": [],
            "workflows": [
                {
                    "id": "wf.api.refinement",
                    "name": "api refinement",
                    "triggers": ["manual"],
                    "steps": [],
                }
            ],
            "views": [],
            "required_modules": ["state.get"],
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
        "/registry/apps/bp.api.refinement.path/install",
        json={"user_id": "api-refinement-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    context_response = client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "open_loops", "key": "api-refinement-followup", "value": {"needed": True}, "tags": ["api"]},
    )
    assert context_response.status_code == 200

    event_response = client.post(
        "/events/publish",
        json={"event_name": "runtime.reviewed", "source": "api-test", "app_instance_id": app_instance_id, "payload": {}},
    )
    assert event_response.status_code == 200

    data_response = client.post(
        f"/data/namespaces/{app_instance_id}:app_data/records",
        json={"key": "api-refinement-log", "value": {"status": "needs refinement"}, "tags": ["api"]},
    )
    assert data_response.status_code == 200

    review_response = client.post("/practice/review", json={"app_instance_id": app_instance_id})
    assert review_response.status_code == 200
    experience_id = review_response.json()["experience"]["experience_id"]

    propose_response = client.post(
        "/self-refinement/propose",
        json={"app_instance_id": app_instance_id, "experience_id": experience_id},
    )
    assert propose_response.status_code == 200

    loop_response = client.post(
        "/self-refinement/loop",
        json={"app_instance_id": app_instance_id, "experience_id": experience_id},
    )
    assert loop_response.status_code == 200
    loop_payload = loop_response.json()
    proposal_id = loop_payload["hypothesis"]["proposal_id"]

    stats_response = client.get(
        "/self-refinement/stats",
        params={"app_instance_id": app_instance_id, "proposal_id": proposal_id},
    )
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["total_hypotheses"] >= 1
    assert stats["total_verifications"] >= 1

    dashboard_response = client.get(
        "/self-refinement/governance-dashboard",
        params={"app_instance_id": app_instance_id, "proposal_id": proposal_id, "recent_limit": 2},
    )
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["overview"]["app_instance_id"] == app_instance_id
    assert dashboard["stats"]["proposal_id"] == proposal_id
    assert dashboard["stats"]["total_hypotheses"] >= 1
    assert isinstance(dashboard["recent_queue"]["items"], list)
    assert isinstance(dashboard["recent_failed_hypotheses"]["items"], list)
