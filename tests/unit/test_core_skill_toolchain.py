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
    telemetry.record_interaction(InteractionTelemetryRecord(interaction_id="pi1", app_id="app.alpha", request_type="prompt_invocation", total_tokens=120, total_latency_ms=40, success=True))
    telemetry.record_interaction(InteractionTelemetryRecord(interaction_id="pi2", app_id="app.alpha", request_type="prompt_invocation", total_tokens=130, total_latency_ms=60, success=False))

    analyzer = CoreCostAnalyzerSkill(telemetry)
    replay = CoreReplaySelectorSkill(telemetry)

    summary = analyzer.summarize_app_cost("app.alpha")
    prompt_summary = analyzer.summarize_prompt_invocation_cost("app.alpha")
    assert summary["interaction_count"] == 4
    assert summary["total_tokens"] == 550
    assert prompt_summary["interaction_count"] == 2
    assert prompt_summary["total_tokens"] == 250
    assert replay.select_failed_interactions() == ["i2", "pi2"]
    assert replay.select_prompt_invocation_interactions(app_id="app.alpha") == ["pi1", "pi2"]
    assert replay.select_prompt_invocation_interactions(app_id="app.alpha", failed_only=True) == ["pi2"]


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
    evaluation.evaluate(
        CandidateEvaluationRecord(
            candidate_id="prompt-invoke:i1",
            target_type="app",
            target_id="app.alpha",
            baseline_version="prompt_invocation.v1",
            candidate_version="prompt_invocation.v2",
            success_delta=0.01,
            token_delta=0.0,
            latency_delta=0.0,
            stability_delta=0.0,
        )
    )
    evaluation.evaluate(
        CandidateEvaluationRecord(
            candidate_id="prompt-invoke:i2",
            target_type="app",
            target_id="app.alpha",
            baseline_version="prompt_invocation.v1",
            candidate_version="prompt_invocation.v2",
            success_delta=-0.10,
            token_delta=0.20,
            latency_delta=0.10,
            stability_delta=-0.10,
        )
    )

    report_skill = CoreAcceptanceReportSkill(evaluation)
    archive_skill = CoreArchiveSummarySkill()

    report = report_skill.build_report("cand.1")
    prompt_report = report_skill.build_prompt_invocation_report("app.alpha")
    archive = archive_skill.summarize_evaluation(record)
    regression = archive_skill.summarize_prompt_invocation_regression(evaluation.list_records())

    assert report["found"] is True
    assert report["accepted"] is True
    assert prompt_report["total_records"] == 2
    assert prompt_report["accepted_records"] == 1
    assert prompt_report["rejected_records"] == 1
    assert archive["candidate_id"] == "cand.1"
    assert regression["record_count"] == 2
    assert regression["rejected_count"] == 1
    assert regression["success_regressions"] == 1
