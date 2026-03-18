from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_context_compaction_api_flow() -> None:
    install_response = client.post(
        "/registry/apps/bp.workspace.assistant/install",
        json={"user_id": "context-compaction-user"},
    )
    assert install_response.status_code == 200
    app_instance_id = install_response.json()["app_instance_id"]

    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "decisions", "key": "use-brief-mode", "value": {"enabled": True}, "tags": ["policy"]},
    )
    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "constraints", "key": "avoid-long-prompts", "value": {"enabled": True}, "tags": ["budget"]},
    )
    client.post(
        f"/app-contexts/{app_instance_id}/entries",
        json={"section": "open_loops", "key": "summarize-context", "value": {"pending": True}, "tags": ["followup"]},
    )

    execute_response = client.post(
        f"/apps/{app_instance_id}/workflows/execute",
        json={"trigger": "api", "inputs": {"topic": "compaction"}},
    )
    assert execute_response.status_code == 200

    compact_response = client.post(f"/app-contexts/{app_instance_id}/compact")
    assert compact_response.status_code == 200
    assert compact_response.json()["layer"] == "summary"
    assert "use-brief-mode" in compact_response.json()["decisions"]
    assert compact_response.json()["metadata"]["context_entry_count"] >= 1

    working_set_response = client.get(f"/app-contexts/{app_instance_id}/working-set")
    assert working_set_response.status_code == 200
    assert working_set_response.json()["layer"] == "working_set"
    assert "summarize-context" in working_set_response.json()["open_loops"]

    layers_response = client.get(f"/app-contexts/{app_instance_id}/layers")
    assert layers_response.status_code == 200
    assert layers_response.json()["layers"]["summary"]["layer"] == "summary"
    assert layers_response.json()["layers"]["detail"]["workflow_history_count"] >= 1
