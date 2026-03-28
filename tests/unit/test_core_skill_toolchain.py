from pathlib import Path

from app.models.evaluation import CandidateEvaluationRecord
from app.models.telemetry import InteractionTelemetryRecord
from app.services.collection_policy_service import CollectionPolicyService
from app.services.core_skill_toolchain import (
    CoreAcceptanceReportSkill,
    CoreArchiveSummarySkill,
    CoreCostAnalyzerSkill,
    CoreReplaySelectorSkill,
)
from app.services.evaluation_summary_service import EvaluationSummaryService
from app.services.runtime_state_store import RuntimeStateStore
from app.services.telemetry_service import TelemetryService
from app.services.upgrade_log_service import UpgradeLogService


def build_services(tmp_path: Path):
    store = RuntimeStateStore(base_dir=str(tmp_path / "store"))
    policies = CollectionPolicyService(store=store)
    logs = UpgradeLogService(base_dir=str(tmp_path / "logs"))
    telemetry = TelemetryService(store=store, policy_service=policies, upgrade_log_service=logs)
    evaluation = EvaluationSummaryService(store=store, upgrade_log_service=logs)
    return telemetry, evaluation


def test_core_cost_analyzer_and_replay_selector(tmp_path: Path) -> None:
    telemetry, _ = build_services(tmp_path)
    telemetry.record_interaction(InteractionTelemetryRecord(interaction_id="i1", app_id="app.alpha", total_tokens=100, total_latency_ms=50, success=True))
    telemetry.record_interaction(InteractionTelemetryRecord(interaction_id="i2", app_id="app.alpha", total_tokens=200, total_latency_ms=70, success=False))

    analyzer = CoreCostAnalyzerSkill(telemetry)
    replay = CoreReplaySelectorSkill(telemetry)

    summary = analyzer.summarize_app_cost("app.alpha")
    assert summary["interaction_count"] == 2
    assert summary["total_tokens"] == 300
    assert replay.select_failed_interactions() == ["i2"]


def test_core_acceptance_report_and_archive_summary(tmp_path: Path) -> None:
    _, evaluation = build_services(tmp_path)
    record = evaluation.evaluate(
        CandidateEvaluationRecord(
            candidate_id="cand.1",
            target_type="skill",
            target_id="skill.alpha",
            baseline_version="1.0.0",
            candidate_version="1.1.0",
            success_delta=0.01,
        )
    )

    report_skill = CoreAcceptanceReportSkill(evaluation)
    archive_skill = CoreArchiveSummarySkill()

    report = report_skill.build_report("cand.1")
    archive = archive_skill.summarize_evaluation(record)

    assert report["found"] is True
    assert report["accepted"] is True
    assert archive["candidate_id"] == "cand.1"
