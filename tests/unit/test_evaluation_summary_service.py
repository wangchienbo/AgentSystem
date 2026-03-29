from datetime import UTC, datetime
from pathlib import Path

from app.models.evaluation import CandidateEvaluationRecord, EvaluationGatePolicy
from app.services.evaluation_summary_service import EvaluationSummaryService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.upgrade_log_service import UpgradeLogService


def test_evaluation_service_accepts_candidate_within_gates(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "store"))
    logs = UpgradeLogService(base_dir=str(tmp_path / "logs"))
    service = EvaluationSummaryService(store=store, upgrade_log_service=logs)

    result = service.evaluate(
        CandidateEvaluationRecord(
            candidate_id="cand.ok",
            target_type="skill",
            target_id="skill.alpha",
            baseline_version="1.0.0",
            candidate_version="1.1.0",
            success_delta=0.03,
            token_delta=0.05,
            latency_delta=0.04,
            stability_delta=0.01,
        )
    )

    assert result.accepted is True
    assert result.rejection_reason == ""
    events = logs.read_events("evaluations", datetime.now(UTC).date().isoformat())
    assert any(item.event_type == "candidate_evaluated" for item in events)


def test_evaluation_service_rejects_candidate_beyond_gates(tmp_path: Path) -> None:
    store = RuntimeStateStore(base_dir=str(tmp_path / "store"))
    logs = UpgradeLogService(base_dir=str(tmp_path / "logs"))
    service = EvaluationSummaryService(store=store, upgrade_log_service=logs)

    result = service.evaluate(
        CandidateEvaluationRecord(
            candidate_id="cand.bad",
            target_type="app",
            target_id="app.alpha",
            baseline_version="1.0.0",
            candidate_version="1.1.0",
            success_delta=-0.10,
            token_delta=0.40,
            latency_delta=0.30,
            stability_delta=-0.10,
        ),
        policy=EvaluationGatePolicy(),
    )

    assert result.accepted is False
    assert "token_growth_exceeded" in result.rejection_reason
    assert "latency_growth_exceeded" in result.rejection_reason
    assert "success_regression_exceeded" in result.rejection_reason
    assert "stability_regression_exceeded" in result.rejection_reason
