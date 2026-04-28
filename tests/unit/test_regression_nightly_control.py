from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from app.bootstrap.runtime import build_runtime
from app.services.regression_nightly_control import (
    REGRESSION_NIGHTLY_SCHEDULE_ID,
    RegressionNightlyControlService,
)
from app.system.regression_governance_policy import (
    build_automation_attention,
    build_automation_risk_flags,
    build_comparison_risk_flags,
    classify_signal_domain,
    recommend_action_for_signal,
    signal_priority,
)
from app.system.regression_governance_observation import (
    build_governance_evidence_digest,
    build_observation_record,
)
from app.system.regression_refinement_translation import build_refinement_payload_from_trigger


def build_service(tmp_path: Path) -> RegressionNightlyControlService:
    services = build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )
    return RegressionNightlyControlService(
        scheduler=services["scheduler"],
        runtime_host=services["runtime_host"],
        runtime_store=services["runtime_store"],
        refinement_memory=services["refinement_memory"],
    )


    attention = build_automation_attention({
        "automation_health": "degraded",
        "attention_reason": "consecutive_failures",
        "last_tick_outcome": "failed",
    })
    assert attention == {
        "health": "degraded",
        "reason": "consecutive_failures",
        "last_tick_outcome": "failed",
    }
    assert build_automation_risk_flags(attention)[0]["signal"] == "nightly_automation_degraded"
    assert classify_signal_domain("nightly_automation_warning") == "automation_control_plane"
    assert classify_signal_domain("elevated_latency") == "regression_quality"
    assert recommend_action_for_signal("nightly_automation_degraded") == "stabilize_nightly_automation_control_plane"
    assert signal_priority({"level": "warning", "signal": "nightly_automation_degraded"}) > signal_priority({"level": "warning", "signal": "elevated_latency"})


def test_comparison_risk_flag_helper_builds_expected_flags() -> None:
    flags = build_comparison_risk_flags({
        "run_count": 2,
        "avg_latency_ms": 6000,
        "avg_fallback_count": 1.2,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"verification_required": 2, "direct": 1},
    })
    signals = {item["signal"] for item in flags}
    assert {"elevated_latency", "elevated_fallback", "elevated_overreach", "conservative_mode_skew"}.issubset(signals)


def test_governance_observation_digest_classifies_failure_stages() -> None:
    digest = build_governance_evidence_digest({
        "summary": {"run_id": "chat-regression-1"},
        "probes": [
            {
                "topic": "api",
                "prompt": "check api",
                "success": True,
                "latency_ms": 1200,
                "response": "需要进一步验证后再下结论",
                "answer_mode": "verification_required",
                "verification_mode": "evidence_required",
                "fallback_like": True,
                "overreach_risk": True,
            },
            {
                "topic": "storage",
                "prompt": "check storage",
                "success": True,
                "latency_ms": 800,
                "response": "请先澄清目标",
                "answer_mode": "clarification_required",
                "verification_mode": "none",
                "fallback_like": False,
                "overreach_risk": False,
            },
        ],
    })

    assert digest.total_observations == 2
    assert digest.failure_stage_counts["evidence"] == 1
    assert digest.failure_stage_counts["requirement_understanding"] == 1
    assert digest.topic_failure_stage_counts["api"]["evidence"] == 1
    assert digest.observation_samples[0].evidence[0].kind == "input"


def test_build_observation_record_emits_structured_evidence() -> None:
    record = build_observation_record("chat-regression-2", {
        "topic": "telemetry",
        "prompt": "check telemetry",
        "success": True,
        "latency_ms": 900,
        "response": "这里还不能直接下结论",
        "answer_mode": "verification_required",
        "verification_mode": "none",
        "fallback_like": False,
        "overreach_risk": True,
    })

    assert record.run_id == "chat-regression-2"
    assert record.failure_stage == "answer_shaping"
    assert [item.kind for item in record.evidence] == ["input", "output", "execution"]


def test_refinement_translation_helper_builds_domain_specific_payloads() -> None:
    automation_payload = build_refinement_payload_from_trigger({
        "signal": "nightly_automation_degraded",
        "domain": "automation_control_plane",
        "recommended_action": "stabilize_nightly_automation_control_plane",
        "detail": "Nightly automation health degraded",
        "level": "warning",
        "failure_stage": "execution",
    })
    regression_payload = build_refinement_payload_from_trigger({
        "signal": "elevated_latency",
        "domain": "regression_quality",
        "recommended_action": "profile_performance_bottlenecks",
        "detail": "Average latency high",
        "level": "warning",
        "failure_stage": "answer_shaping",
    })

    assert automation_payload["queue_note"] == "automation_control_plane::stabilize_nightly_automation_control_plane::execution"
    assert "Automation control-plane risk" in automation_payload["novelty_note"]
    assert regression_payload["queue_note"] == "regression_quality::profile_performance_bottlenecks::answer_shaping"
    assert "Regression-quality risk" in regression_payload["novelty_note"]


def test_build_nightly_status_exposes_due_state(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    record = service.register_nightly_schedule(interval_seconds=3600)
    record.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)

    status = service.build_nightly_status({"running": False})

    assert status["registered"] is True
    assert status["due_now"] is True
    assert REGRESSION_NIGHTLY_SCHEDULE_ID in status["due_schedule_ids"]
    assert status["automation_control"]["schedule_registered"] is True


def test_trigger_due_tick_skips_when_not_due(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)

    result = service.trigger_due_tick(client=Mock(), driver_status={"running": False})

    assert result["triggered"] is False
    assert result["nightly_status"]["last_tick_decision"] == "skipped_not_due"


def test_trigger_due_tick_executes_when_due(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    record = service.register_nightly_schedule(interval_seconds=3600)
    record.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)
    service.run_cycle = Mock(return_value={"run_id": "svc-nightly-run"})

    result = service.trigger_due_tick(client=Mock(), driver_status={"running": True})

    assert result["triggered"] is True
    assert result["cycle"]["run_id"] == "svc-nightly-run"
    assert result["nightly_status"]["last_tick_decision"] == "triggered_due"


def test_trigger_manual_cycle_returns_not_triggered_when_scheduler_no_match(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    result = service.trigger_manual_cycle(client=Mock())
    assert result["triggered"] is False
    assert isinstance(result["schedule_results"], list)


def test_trigger_manual_cycle_executes_and_clears_pending_when_schedule_matches(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)
    service.run_cycle = Mock(return_value={"run_id": "manual-run-1"})

    result = service.trigger_manual_cycle(client=Mock())

    assert result["triggered"] is True
    assert result["cycle"]["run_id"] == "manual-run-1"


def test_build_nightly_status_exposes_automation_control_card(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)

    status = service.build_nightly_status({"running": True, "interval_seconds": 60})

    assert "automation_control" in status
    assert status["automation_control"]["driver"]["running"] is True
    assert status["automation_control"]["schedule_registered"] is True
    assert status["automation_control"]["last_tick_outcome"] == "skipped"
    assert status["automation_control"]["automation_health"] == "healthy"
    assert status["automation_control"]["attention_reason"] == ""


def test_trigger_due_tick_records_no_trigger_match(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    record = service.register_nightly_schedule(interval_seconds=3600)
    record.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)
    service._scheduler.trigger_interval_schedules = Mock(return_value=[])

    result = service.trigger_due_tick(client=Mock(), driver_status={"running": False})

    assert result["triggered"] is False
    assert result["nightly_status"]["last_tick_decision"] == "skipped_no_trigger_match"


def test_trigger_due_tick_propagates_cycle_failure_and_records_failed_state(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    record = service.register_nightly_schedule(interval_seconds=3600)
    record.last_triggered_at = datetime.now(UTC) - timedelta(seconds=7200)

    def _boom(client):
        raise RuntimeError("cycle failed")

    service.run_cycle = _boom

    try:
        service.trigger_due_tick(client=Mock(), driver_status={"running": True})
    except RuntimeError as exc:
        assert str(exc) == "cycle failed"
    else:
        raise AssertionError("expected RuntimeError")

    state = service.load_tick_state()
    assert state["last_tick_decision"] == "failed_cycle"
    assert state["last_cycle_result"]["error_type"] == "RuntimeError"
    assert state["consecutive_failures"] == 1
    assert state["retry_pending"] is True


def test_build_nightly_status_exposes_failure_fields_in_automation_control(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)
    service.save_tick_state({
        "last_tick_at": "2026-04-28T00:00:00Z",
        "last_tick_decision": "failed_cycle",
        "last_tick_triggered": False,
        "last_cycle_result": {"error": "cycle failed", "error_type": "RuntimeError"},
    })

    status = service.build_nightly_status({"running": False})

    assert status["automation_control"]["last_tick_outcome"] == "failed"
    assert status["automation_control"]["last_cycle_error"] == "cycle failed"
    assert status["automation_control"]["last_cycle_error_type"] == "RuntimeError"


def test_record_tick_marks_degraded_after_consecutive_failures(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.record_tick(decision="failed_cycle", triggered=False, cycle={"error": "one"})
    state = service.record_tick(decision="failed_cycle", triggered=False, cycle={"error": "two"})

    assert state["consecutive_failures"] == 2
    assert state["degraded"] is True
    assert state["retry_pending"] is True


def test_successful_trigger_resets_failure_counters(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.record_tick(decision="failed_cycle", triggered=False, cycle={"error": "one"})
    state = service.record_tick(decision="triggered_due", triggered=True, cycle={"run_id": "ok"})

    assert state["consecutive_failures"] == 0
    assert state["degraded"] is False
    assert state["retry_pending"] is False


def test_build_nightly_status_exposes_recovery_fields_in_automation_control(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.save_tick_state({
        "last_tick_at": "2026-04-28T00:00:00Z",
        "last_tick_decision": "failed_cycle",
        "last_tick_triggered": False,
        "last_cycle_result": {"error": "cycle failed", "error_type": "RuntimeError"},
        "last_failure_at": "2026-04-28T00:00:00Z",
        "consecutive_failures": 2,
        "degraded": True,
        "retry_pending": True,
    })

    status = service.build_nightly_status({"running": False})

    assert status["automation_control"]["degraded"] is True
    assert status["automation_control"]["retry_pending"] is True
    assert status["automation_control"]["consecutive_failures"] == 2
    assert status["automation_control"]["automation_health"] == "degraded"
    assert status["automation_control"]["attention_reason"] == "consecutive_failures"


def test_build_nightly_status_exposes_warning_health_for_retry_pending(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.save_tick_state({
        "last_tick_at": "2026-04-28T00:00:00Z",
        "last_tick_decision": "failed_cycle",
        "last_tick_triggered": False,
        "last_cycle_result": {"error": "cycle failed", "error_type": "RuntimeError"},
        "last_failure_at": "2026-04-28T00:00:00Z",
        "consecutive_failures": 1,
        "degraded": False,
        "retry_pending": True,
    })

    status = service.build_nightly_status({"running": False})

    assert status["automation_control"]["automation_health"] == "warning"
    assert status["automation_control"]["attention_reason"] == "retry_pending"


def test_regression_dashboard_maps_automation_attention() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_governance_dashboard, build_regression_operator_summary

    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value={"run_count": 1, "avg_latency_ms": 0, "avg_fallback_count": 0, "avg_overreach_risk_count": 0, "answer_mode_totals": {}, "verification_mode_totals": {}}), \
         patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 1}), \
         patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        dashboard = build_regression_governance_dashboard(nightly_status=nightly_status)
        summary = build_regression_operator_summary(nightly_status=nightly_status)

    assert dashboard["automation_attention"]["health"] == "degraded"
    assert any(flag["signal"] == "nightly_automation_degraded" for flag in dashboard["risk_flags"])
    assert summary["refinement"]["governance"]["automation_attention"]["reason"] == "consecutive_failures"
    assert summary["refinement"]["recommended_action"] == "stabilize_nightly_automation_control_plane"
    assert summary["refinement"]["priority_domain"] == "automation_control_plane"
    assert summary["refinement"]["priority_signal"] == "nightly_automation_degraded"
    assert summary["refinement"]["primary_contradiction"] == "automation_control_plane: nightly_automation_degraded"


def test_operator_summary_prioritizes_automation_degraded_over_other_warning_signals() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_operator_summary

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.2,
        "answer_mode_totals": {"direct": 2, "verification_required": 2},
        "verification_mode_totals": {},
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison), \
         patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {"api": []}, "run_count": 3}), \
         patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(nightly_status=nightly_status)

    assert summary["refinement"]["priority_domain"] == "automation_control_plane"
    assert summary["refinement"]["priority_signal"] == "nightly_automation_degraded"
    assert summary["refinement"]["recommended_action"] == "stabilize_nightly_automation_control_plane"


def test_governance_dashboard_aggregates_regression_and_automation_signals() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_governance_dashboard

    comparison = {
        "run_count": 4,
        "avg_latency_ms": 7000,
        "avg_fallback_count": 1.2,
        "avg_overreach_risk_count": 0.8,
        "answer_mode_totals": {"direct": 1, "verification_required": 3},
        "verification_mode_totals": {"required": 3},
    }
    trends = {"topics": {"api": [{"run_id": "r1"}]}, "run_count": 4}
    evidence = [{"summary": "e1"}]
    nightly_status = {
        "automation_control": {
            "automation_health": "warning",
            "attention_reason": "retry_pending",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison), \
         patch("app.system.regression_dashboard.build_topic_trends", return_value=trends), \
         patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=evidence):
        dashboard = build_regression_governance_dashboard(nightly_status=nightly_status)

    signals = {item["signal"] for item in dashboard["risk_flags"]}
    assert dashboard["comparison"] == comparison
    assert dashboard["trends"] == trends
    assert dashboard["evidence"] == evidence
    assert dashboard["automation_attention"]["reason"] == "retry_pending"
    assert {"elevated_latency", "elevated_fallback", "elevated_overreach", "nightly_automation_warning"}.issubset(signals)


def test_regression_triggers_include_automation_warning_signal() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_triggers

    nightly_status = {
        "automation_control": {
            "automation_health": "warning",
            "attention_reason": "retry_pending",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value={"run_count": 1, "avg_latency_ms": 0, "avg_fallback_count": 0, "avg_overreach_risk_count": 0, "answer_mode_totals": {}, "verification_mode_totals": {}}), \
         patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 1}), \
         patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        warning_payload = build_regression_triggers(threshold="info", nightly_status=nightly_status)
        warning_only = build_regression_triggers(threshold="warning", nightly_status=nightly_status)

    assert any(item["signal"] == "nightly_automation_warning" for item in warning_payload["triggers"])
    assert all(item["signal"] != "nightly_automation_warning" for item in warning_only["triggers"])
    assert any(item["recommended_action"] == "inspect_nightly_automation_recovery_path" for item in warning_payload["triggers"])
    assert any(item["domain"] == "automation_control_plane" for item in warning_payload["triggers"])


def test_apply_regression_triggers_to_refinement_uses_domain_specific_payloads(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import apply_regression_triggers_to_refinement

    services = build_runtime(
        runtime_store_base_dir=str(tmp_path / "runtime"),
        app_data_base_dir=str(tmp_path / "namespaces"),
    )
    memory = services["refinement_memory"]
    comparison = {
        "run_count": 2,
        "avg_latency_ms": 6200,
        "avg_fallback_count": 0,
        "avg_overreach_risk_count": 0,
        "answer_mode_totals": {"direct": 1, "verification_required": 1},
        "verification_mode_totals": {},
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison), \
         patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 2}), \
         patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        payload = apply_regression_triggers_to_refinement(memory, nightly_status=nightly_status)

    contradictions = {item["contradiction"] for item in payload["created_hypotheses"]}
    queue_notes = {item["note"] for item in payload["created_queue_items"]}
    novelty_notes = {item["novelty_note"] for item in payload["created_hypotheses"]}
    verification_summaries = {item["summary"] for item in payload["created_verifications"]}

    assert "automation_control_plane: nightly_automation_degraded" in contradictions
    assert "regression_quality: elevated_latency" in contradictions
    assert "automation_control_plane::stabilize_nightly_automation_control_plane::execution" in queue_notes
    assert "regression_quality::profile_performance_bottlenecks::execution" in queue_notes
    assert any("Automation control-plane risk" in item for item in novelty_notes)
    assert any("Regression-quality risk" in item for item in novelty_notes)
    assert any("Automation control-plane attention recorded" in item for item in verification_summaries)


def test_regression_dashboard_exposes_observation_digest() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_governance_dashboard

    comparison = {
        "run_count": 1,
        "avg_latency_ms": 1000,
        "avg_fallback_count": 1,
        "avg_overreach_risk_count": 1,
        "answer_mode_totals": {"verification_required": 1},
        "verification_mode_totals": {"evidence_required": 1},
        "runs": [{"summary": {"run_id": "chat-regression-obs-1"}}],
    }
    run_detail = {
        "summary": {"run_id": "chat-regression-obs-1"},
        "probes": [{
            "topic": "api",
            "prompt": "check api",
            "success": True,
            "latency_ms": 1000,
            "response": "需要进一步验证",
            "answer_mode": "verification_required",
            "verification_mode": "evidence_required",
            "fallback_like": True,
            "overreach_risk": True,
        }],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison), \
         patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 1}), \
         patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]), \
         patch("app.system.regression_dashboard.read_run_details", return_value=run_detail):
        dashboard = build_regression_governance_dashboard()

    assert dashboard["observation_digest"]["total_observations"] == 1
    assert dashboard["observation_digest"]["failure_stage_counts"]["evidence"] == 1


def test_regression_triggers_propagate_failure_stage_from_observation_digest() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_triggers

    dashboard = {
        "comparison": {"run_count": 1},
        "risk_flags": [
            {"signal": "elevated_overreach", "level": "warning", "detail": "Overreach risk high"},
            {"signal": "elevated_latency", "level": "warning", "detail": "Latency high"},
        ],
        "observation_digest": {
            "total_observations": 2,
            "failure_stage_counts": {
                "answer_shaping": 1,
                "execution": 1,
            },
            "topic_failure_stage_counts": {},
            "observation_samples": [],
        },
    }

    with patch("app.system.regression_dashboard.build_regression_governance_dashboard", return_value=dashboard):
        payload = build_regression_triggers()

    stage_by_signal = {item["signal"]: item["failure_stage"] for item in payload["triggers"]}
    assert stage_by_signal["elevated_overreach"] == "answer_shaping"
    assert stage_by_signal["elevated_latency"] == "execution"
