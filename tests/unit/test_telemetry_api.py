from fastapi.testclient import TestClient

from app.api.main import app, telemetry_service, evaluation_summary_service
from app.models.evaluation import CandidateEvaluationRecord
from app.models.telemetry import FeedbackRecord, InteractionTelemetryRecord, VersionBindingRecord

client = TestClient(app)


def test_telemetry_and_evaluation_read_apis() -> None:
    telemetry_service.record_interaction(
        InteractionTelemetryRecord(interaction_id="api.i.1", app_id="app.api", total_tokens=123, success=True)
    )
    telemetry_service.record_feedback(
        FeedbackRecord(
            feedback_id="api.f.1",
            interaction_id="api.i.1",
            scope_type="app",
            scope_id="app.api",
            feedback_kind="explicit",
            score=5,
        ),
        app_id="app.api",
    )
    telemetry_service.bind_versions(
        VersionBindingRecord(interaction_id="api.i.1", app_version="1.0.0"),
        app_id="app.api",
    )
    evaluation_summary_service.evaluate(
        CandidateEvaluationRecord(
            candidate_id="api.c.1",
            target_type="app",
            target_id="app.api",
            baseline_version="1.0.0",
            candidate_version="1.1.0",
            success_delta=0.02,
        )
    )

    response = client.get("/telemetry/interactions/api.i.1")
    assert response.status_code == 200
    assert response.json()["interaction_id"] == "api.i.1"

    feedback = client.get("/telemetry/feedback", params={"scope_id": "app.api"})
    assert feedback.status_code == 200
    assert len(feedback.json()) >= 1

    binding = client.get("/telemetry/version-bindings/api.i.1")
    assert binding.status_code == 200
    assert binding.json()["app_version"] == "1.0.0"

    candidate = client.get("/evaluation/candidates/api.c.1")
    assert candidate.status_code == 200
    assert candidate.json()["candidate_id"] == "api.c.1"


def test_core_skill_read_apis() -> None:
    telemetry_service.record_interaction(
        InteractionTelemetryRecord(interaction_id="api.i.2", app_id="app.core", total_tokens=200, total_latency_ms=40, success=False)
    )
    evaluation_summary_service.evaluate(
        CandidateEvaluationRecord(
            candidate_id="api.c.2",
            target_type="skill",
            target_id="skill.core",
            baseline_version="1.0.0",
            candidate_version="1.1.0",
            success_delta=0.01,
        )
    )

    replay = client.get("/core-skills/replay/failed-interactions")
    assert replay.status_code == 200
    assert "api.i.2" in replay.json()["interaction_ids"]

    cost = client.get("/core-skills/cost/app.core")
    assert cost.status_code == 200
    assert cost.json()["interaction_count"] >= 1

    acceptance = client.get("/core-skills/acceptance/api.c.2")
    assert acceptance.status_code == 200
    assert acceptance.json()["candidate_id"] == "api.c.2"

    archive = client.get("/core-skills/archive/api.c.2")
    assert archive.status_code == 200
    assert archive.json()["candidate_id"] == "api.c.2"
