from pathlib import Path

from tests.unit.api_test_helper import create_isolated_test_client


def test_evidence_api_lists_signals_and_promoted_entries(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    log_evidence = client.app.state.services["log_evidence"]
    log_evidence.ingest_workflow_failure(
        app_instance_id="app.api",
        workflow_id="wf.api",
        failed_step_ids=["step.1"],
        execution_id="exec.1",
        status="partial",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id="app.api",
        workflow_id="wf.api",
        failed_step_ids=["step.1"],
        execution_id="exec.2",
        status="partial",
    )
    log_evidence.ingest_workflow_failure(
        app_instance_id="app.api",
        workflow_id="wf.api",
        failed_step_ids=["step.1"],
        execution_id="exec.3",
        status="partial",
    )

    signals = client.get("/evidence/signals")
    promoted = client.get("/evidence/promoted")
    index_payload = client.get("/evidence/index")
    stats = client.get("/evidence/stats")

    assert signals.status_code == 200
    assert promoted.status_code == 200
    assert index_payload.status_code == 200
    assert stats.status_code == 200
    assert len(signals.json()["items"]) >= 1
    assert len(promoted.json()["items"]) >= 1
    assert len(index_payload.json()["items"]) >= 1
    assert stats.json()["signal_count"] >= 1



def test_clarify_unresolved_can_feed_evidence_pipeline(tmp_path: Path) -> None:
    client = create_isolated_test_client(tmp_path)
    log_evidence = client.app.state.services["log_evidence"]
    log_evidence.ingest_clarify_unresolved(
        request_text="做一个系统",
        requirement_type="unclear",
        readiness="needs_clarification",
        missing_fields=["artifact_type", "goal"],
    )
    log_evidence.ingest_clarify_unresolved(
        request_text="做一个系统",
        requirement_type="unclear",
        readiness="needs_clarification",
        missing_fields=["artifact_type", "goal"],
    )

    signals = client.get("/evidence/signals")
    assert signals.status_code == 200
    assert any(item["category"] == "clarify_unresolved" for item in signals.json()["items"])
