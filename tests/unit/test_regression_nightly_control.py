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
    PREFLIGHT_HOLD_AUTOMATION_DEGRADED_REQUIRES_REVIEW,
    PREFLIGHT_HOLD_AUTOMATION_RETRY_PENDING_REQUIRES_REVIEW,
    PREFLIGHT_HOLD_SECONDARY_REQUIRES_REVIEW,
    PREFLIGHT_REVIEW_REASON_AUTOMATION_DEGRADED,
    PREFLIGHT_REVIEW_REASON_AUTOMATION_RETRY_PENDING,
    PREFLIGHT_REVIEW_REASON_PRIMARY_SELECTION_HEALTHY,
    PREFLIGHT_REVIEW_REASON_PRIORITY_SECONDARY,
    PREFLIGHT_REVIEW_SCOPE_LIGHT_AUTO_APPLY_OK,
    PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_AUTOMATION,
    PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_QUEUE_STATE,
)
from app.system.regression_governance_policy import (
    build_automation_attention,
    format_governance_preflight_badge,
    format_governance_preflight_operator_note,
    build_automation_risk_flags,
    build_comparison_risk_flags,
    classify_signal_domain,
    classify_signal_family,
    classify_signal_subdomain_candidate,
    recommend_action_for_signal,
    signal_priority,
)
from app.system.regression_governance_observation import (
    build_governance_evidence_digest,
    build_observation_record,
    build_replay_observation_digest,
)
from app.system.chat_observation import build_chat_observation_digest, persist_chat_observation
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
        refinement_rollout=services.get("refinement_rollout"),
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
    assert classify_signal_family("nightly_automation_degraded") == "automation_recovery"
    assert classify_signal_family("elevated_overreach") == "answer_shaping"
    assert classify_signal_subdomain_candidate("elevated_latency") == "latency_path"
    assert classify_signal_subdomain_candidate("conservative_mode_skew") == "clarification_threshold"
    assert recommend_action_for_signal("nightly_automation_degraded") == "stabilize_nightly_automation_control_plane"
    assert signal_priority({"level": "warning", "signal": "nightly_automation_degraded"}) > signal_priority({"level": "warning", "signal": "elevated_latency"})


def test_governance_preflight_pipeline_prioritizes_availability_before_selection() -> None:
    from app.models.governance_preflight import GovernancePreflightContext
    from app.system.regression_governance_policy import evaluate_governance_preflight

    decision = evaluate_governance_preflight(GovernancePreflightContext(
        recommended_queue_id=None,
        priority_tier="primary",
        rollout_available=False,
        queue_status=None,
    ))

    assert decision.hold_reason == "rollout_service_unavailable"
    assert decision.matched_stage == "availability_gate"
    assert decision.decision_code == "availability.rollout_unavailable"
    assert decision.decision_label == "Rollout service unavailable"
    assert "stage=availability_gate" in decision.decision_summary


def test_governance_preflight_evaluator_blocks_missing_queue() -> None:
    from app.models.governance_preflight import GovernancePreflightContext
    from app.system.regression_governance_policy import evaluate_governance_preflight

    decision = evaluate_governance_preflight(GovernancePreflightContext(
        recommended_queue_id="q-missing",
        priority_tier="primary",
        rollout_available=True,
        queue_status=None,
    ))

    assert decision.can_apply is False
    assert decision.hold_reason == "recommended_queue_missing"
    assert decision.matched_stage == "queue_state_gate"
    assert decision.decision_code == "queue_state.queue_record_missing"
    assert decision.decision_label == "Recommended queue record missing"


def test_governance_preflight_decision_builder_returns_typed_payload() -> None:
    from app.models.governance_preflight import GovernancePreflightDecision
    from app.system.regression_governance_policy import build_governance_preflight_decision

    decision = build_governance_preflight_decision(
        base={"recommended_queue_id": "q1", "priority_tier": "primary"},
        can_apply=True,
        apply_risk="medium",
        hold_reason="",
        review_scope=PREFLIGHT_REVIEW_SCOPE_LIGHT_AUTO_APPLY_OK,
        review_reason=PREFLIGHT_REVIEW_REASON_PRIMARY_SELECTION_HEALTHY,
        matched_stage="tier_gate",
        decision_code="tier.primary_auto_apply",
        queue_status="queued",
    )

    assert isinstance(decision, GovernancePreflightDecision)
    assert decision.review_scope == PREFLIGHT_REVIEW_SCOPE_LIGHT_AUTO_APPLY_OK
    assert decision.to_payload()["hold_category"] == "none"
    assert decision.to_payload()["matched_stage"] == "tier_gate"
    assert decision.to_payload()["decision_code"] == "tier.primary_auto_apply"
    assert decision.to_payload()["decision_label"] == "Primary tier auto-apply allowed"
    assert decision.to_payload()["render_badge"] == "AUTO | Primary tier auto-apply allowed"
    assert "code=tier.primary_auto_apply" in decision.to_payload()["render_operator_note"]


def test_governance_preflight_render_helpers_return_shared_operator_strings() -> None:
    from app.system.regression_governance_policy import build_governance_preflight_decision

    decision = build_governance_preflight_decision(
        base={"recommended_queue_id": "q1", "priority_tier": "secondary"},
        can_apply=False,
        apply_risk="medium",
        hold_reason="secondary_requires_review",
        review_scope="operator_review_required",
        review_reason="priority_secondary",
        matched_stage="tier_gate",
        decision_code="tier.secondary_requires_review",
        queue_status="queued",
    )

    assert format_governance_preflight_badge(decision) == "HOLD | Secondary tier review required"
    note = format_governance_preflight_operator_note(decision)
    assert "code=tier.secondary_requires_review" in note
    assert "stage=tier_gate" in note
    assert "queue=q1" in note


def test_governance_rollout_operator_summary_builds_applied_and_hold_views() -> None:
    from app.system.regression_governance_policy import build_governance_rollout_operator_summary

    applied = build_governance_rollout_operator_summary({
        "applied": True,
        "queue_id": "q-primary",
        "preflight": {
            "recommended_queue_id": "q-primary",
            "hold_reason": "",
            "review_scope": "light_auto_apply_ok",
            "review_reason": "primary_selection_healthy",
            "decision_code": "tier.primary_auto_apply",
            "decision_label": "Primary tier auto-apply allowed",
            "render_badge": "AUTO | Primary tier auto-apply allowed",
            "render_operator_note": "AUTO | Primary tier auto-apply allowed | code=tier.primary_auto_apply",
        },
    })
    held = build_governance_rollout_operator_summary({
        "applied": False,
        "reason": "secondary_requires_review",
        "preflight": {
            "recommended_queue_id": "q-secondary",
            "hold_reason": "secondary_requires_review",
            "review_scope": "operator_review_required",
            "review_reason": "priority_secondary",
            "decision_code": "tier.secondary_requires_review",
            "decision_label": "Secondary tier review required",
            "render_badge": "HOLD | Secondary tier review required",
            "render_operator_note": "HOLD | Secondary tier review required | code=tier.secondary_requires_review",
        },
    })

    assert applied == {
        "decision": "auto_applied",
        "action": "applied_selected_queue",
        "queue_id": "q-primary",
        "applied": True,
        "reason": None,
        "review_scope": "light_auto_apply_ok",
        "review_reason": "primary_selection_healthy",
        "decision_code": "tier.primary_auto_apply",
        "decision_label": "Primary tier auto-apply allowed",
        "render_badge": "AUTO | Primary tier auto-apply allowed",
        "render_operator_note": "AUTO | Primary tier auto-apply allowed | code=tier.primary_auto_apply",
    }
    assert held["decision"] == "held"
    assert held["action"] == "operator_review_required"
    assert held["queue_id"] == "q-secondary"
    assert held["reason"] == "secondary_requires_review"
    assert held["decision_code"] == "tier.secondary_requires_review"


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

    assert automation_payload["queue_note"] == "automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=normal"
    assert "Automation control-plane risk" in automation_payload["novelty_note"]
    assert "family=automation_recovery" in automation_payload["novelty_note"]
    assert "priority_tier=normal" in automation_payload["novelty_note"]
    assert regression_payload["queue_note"] == "regression_quality::execution_semantics::profile_performance_bottlenecks::answer_shaping::priority=normal"
    assert "Regression-quality risk" in regression_payload["novelty_note"]
    assert "family=execution_semantics" in regression_payload["novelty_note"]
    assert "priority_tier=normal" in regression_payload["novelty_note"]


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
    assert summary["refinement"]["priority_family"] == "automation_recovery"
    assert summary["refinement"]["priority_subdomain_candidate"] == "degraded_guard"
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
    assert summary["refinement"]["priority_family"] == "automation_recovery"
    assert summary["refinement"]["priority_subdomain_candidate"] == "degraded_guard"
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
    assert "automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary" in queue_notes
    assert "regression_quality::execution_semantics::profile_performance_bottlenecks::execution::priority=secondary" in queue_notes
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
    family_by_signal = {item["signal"]: item["family"] for item in payload["triggers"]}
    assert stage_by_signal["elevated_overreach"] == "answer_shaping"
    assert stage_by_signal["elevated_latency"] == "execution"
    subdomain_by_signal = {item["signal"]: item["subdomain_candidate"] for item in payload["triggers"]}
    assert family_by_signal["elevated_overreach"] == "answer_shaping"
    assert family_by_signal["elevated_latency"] == "execution_semantics"
    assert subdomain_by_signal["elevated_overreach"] == "overreach_boundary"
    assert subdomain_by_signal["elevated_latency"] == "latency_path"


def test_replay_observation_digest_builds_from_recent_history() -> None:
    digest = build_replay_observation_digest("session-replay-1", [
        {"role": "user", "content": "为什么这个接口这样设计"},
        {"role": "assistant", "content": "这里还需要进一步验证后再下结论"},
        {"role": "assistant", "content": "请先澄清你的目标"},
        {"role": "assistant", "content": "已经确认完成"},
    ], limit=3)

    assert digest.total_observations == 3
    assert digest.failure_stage_counts["evidence"] == 1
    assert digest.failure_stage_counts["requirement_understanding"] == 1
    assert digest.observation_samples[0].evidence[0].source == "conversation_history_replay"


def test_regression_dashboard_exposes_replay_observation_digest() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_governance_dashboard

    comparison = {
        "run_count": 1,
        "avg_latency_ms": 1000,
        "avg_fallback_count": 0,
        "avg_overreach_risk_count": 0,
        "answer_mode_totals": {"direct": 1},
        "verification_mode_totals": {"none": 1},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 1}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        dashboard = build_regression_governance_dashboard(
            replay_session_id="session-replay-2",
            replay_history=[
                {"role": "assistant", "content": "需要进一步验证后再判断"},
                {"role": "assistant", "content": "请先澄清目标"},
            ],
        )

    assert dashboard["replay_observation_digest"]["total_observations"] == 2
    assert dashboard["replay_observation_digest"]["failure_stage_counts"]["evidence"] == 1


def test_operator_summary_exposes_family_breakdown() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_operator_summary

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 2, "verification_required": 2},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {"api": []}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(nightly_status=nightly_status)

    breakdown = summary["refinement"]["governance"]["family_breakdown"]
    assert breakdown["counts"]["automation_recovery"] == 1
    assert breakdown["counts"]["execution_semantics"] >= 1
    assert breakdown["latest_items"]["automation_recovery"]["domain"] == "automation_control_plane"


def test_operator_summary_exposes_family_queue_lane_summary() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_operator_summary

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(nightly_status=nightly_status)

    lane_summary = summary["refinement"]["governance"]["family_queue_lane_summary"]
    assert lane_summary["family_counts"]["automation_recovery"] == 1
    assert lane_summary["family_warning_counts"]["automation_recovery"] == 1
    assert lane_summary["action_counts"]["execution_semantics"]["profile_performance_bottlenecks"] >= 1
    assert lane_summary["latest_lane_items"]["automation_recovery::stabilize_nightly_automation_control_plane"]["signal"] == "nightly_automation_degraded"


def test_operator_summary_exposes_priority_subdomain_candidate_and_family_metadata() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_operator_summary

    comparison = {
        "run_count": 2,
        "avg_latency_ms": 6200,
        "avg_fallback_count": 1.2,
        "avg_overreach_risk_count": 0.8,
        "answer_mode_totals": {"verification_required": 2},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 2}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(nightly_status=nightly_status)

    assert summary["refinement"]["priority_subdomain_candidate"] == "degraded_guard"
    assert summary["refinement"]["governance"]["family_breakdown"]["latest_items"]["automation_recovery"]["subdomain_candidate"] == "degraded_guard"
    lane = summary["refinement"]["governance"]["family_queue_lane_summary"]["latest_lane_items"]["automation_recovery::stabilize_nightly_automation_control_plane"]
    assert lane["subdomain_candidate"] == "degraded_guard"


def test_operator_summary_exposes_subdomain_breakdown() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_operator_summary

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(nightly_status=nightly_status)

    breakdown = summary["refinement"]["governance"]["subdomain_breakdown"]
    assert breakdown["counts"]["degraded_guard"] == 1
    assert breakdown["warning_counts"]["degraded_guard"] == 1
    assert breakdown["family_map"]["degraded_guard"] == "automation_recovery"
    assert breakdown["latest_items"]["degraded_guard"]["signal"] == "nightly_automation_degraded"


def test_operator_summary_exposes_cross_level_governance_summary() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_operator_summary

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(nightly_status=nightly_status)

    cross = summary["refinement"]["governance"]["cross_level_summary"]
    assert cross["priority_lane"] == "automation_recovery::stabilize_nightly_automation_control_plane"
    assert "degraded_guard" in cross["family_to_subdomains"]["automation_recovery"]
    assert cross["subdomain_to_latest_lane"]["degraded_guard"] == "automation_recovery::stabilize_nightly_automation_control_plane"
    assert cross["family_warning_density"]["automation_recovery"] == 1.0
    assert cross["subdomain_warning_density"]["degraded_guard"] == 1.0


def test_build_nightly_status_exposes_governance_attention_consumer(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)
    service.record_tick(decision="failed_cycle", triggered=False, cycle={"error": "boom"}, nightly_status={})
    service.record_tick(decision="failed_cycle", triggered=False, cycle={"error": "boom-again"}, nightly_status={})

    from unittest.mock import patch
    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        status = service.build_nightly_status({"running": False})

    attention = status["automation_control"]["governance_attention"]
    assert attention["priority_family"] == "automation_recovery"
    assert attention["priority_subdomain_candidate"] == "degraded_guard"
    assert attention["priority_lane"] == "automation_recovery::stabilize_nightly_automation_control_plane"
    assert attention["recommended_action"] == "stabilize_nightly_automation_control_plane"


def test_regression_triggers_include_governance_priority_hints() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_triggers

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        payload = build_regression_triggers(nightly_status=nightly_status)

    priority_by_signal = {item["signal"]: item["governance_priority"]["suggested_priority_tier"] for item in payload["triggers"]}
    assert priority_by_signal["nightly_automation_degraded"] == "primary"
    assert priority_by_signal["elevated_latency"] == "secondary"


def test_operator_summary_exposes_governance_prioritized_queue_view(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem
    from app.system.regression_dashboard import build_regression_operator_summary

    service = build_service(tmp_path)
    memory = service._refinement_memory
    memory.add_queue_item(RolloutQueueItem(
        queue_id="q-normal",
        hypothesis_id="h1",
        proposal_id="p1",
        app_instance_id="agent_system",
        status="queued",
        note="regression_quality::execution_semantics::profile_performance_bottlenecks::execution::priority=normal",
    ))
    memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h2",
        proposal_id="p2",
        app_instance_id="agent_system",
        status="queued",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))
    memory.add_queue_item(RolloutQueueItem(
        queue_id="q-secondary",
        hypothesis_id="h3",
        proposal_id="p3",
        app_instance_id="agent_system",
        status="queued",
        note="regression_quality::execution_semantics::profile_performance_bottlenecks::execution::priority=secondary",
    ))

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(memory=memory)

    view = summary["refinement"]["governance"]["prioritized_queue_view"]
    assert [item["queue_id"] for item in view["items"]] == ["q-primary", "q-secondary", "q-normal"]
    assert view["priority_counts"] == {"primary": 1, "secondary": 1, "normal": 1}


def test_operator_summary_exposes_governance_rollout_selection(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem
    from app.system.regression_dashboard import build_regression_operator_summary

    service = build_service(tmp_path)
    memory = service._refinement_memory
    memory.add_queue_item(RolloutQueueItem(
        queue_id="q-normal",
        hypothesis_id="h1",
        proposal_id="p1",
        app_instance_id="agent_system",
        status="queued",
        note="regression_quality::execution_semantics::profile_performance_bottlenecks::execution::priority=normal",
    ))
    memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h2",
        proposal_id="p2",
        app_instance_id="agent_system",
        status="queued",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(memory=memory)

    selection = summary["refinement"]["governance"]["rollout_selection"]
    assert selection["recommended_queue_id"] == "q-primary"
    assert selection["recommended_priority_tier"] == "primary"
    assert selection["selection_reason"] == "highest_governance_priority:primary"


def test_operator_summary_exposes_governance_rollout_review_packet(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem
    from app.system.regression_dashboard import build_regression_operator_summary

    service = build_service(tmp_path)
    memory = service._refinement_memory
    memory.add_queue_item(RolloutQueueItem(
        queue_id="q-normal",
        hypothesis_id="h1",
        proposal_id="p1",
        app_instance_id="agent_system",
        status="queued",
        note="regression_quality::execution_semantics::profile_performance_bottlenecks::execution::priority=normal",
    ))
    memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h2",
        proposal_id="p2",
        app_instance_id="agent_system",
        status="queued",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(memory=memory, nightly_status=nightly_status)

    packet = summary["refinement"]["governance"]["rollout_review_packet"]
    assert packet["recommended_queue_id"] == "q-primary"
    assert packet["recommended_priority_tier"] == "primary"
    assert packet["selection_reason"] == "highest_governance_priority:primary"
    assert packet["priority_lane"] == "automation_recovery::stabilize_nightly_automation_control_plane"
    assert packet["recommended_action"] == "stabilize_nightly_automation_control_plane"
    assert packet["top_queue_note"] == "automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary"
    assert packet["automation_attention"]["reason"] == "consecutive_failures"


def test_operator_summary_exposes_governance_rollout_review_card(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem
    from app.system.regression_dashboard import build_regression_operator_summary

    service = build_service(tmp_path)
    memory = service._refinement_memory
    memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h2",
        proposal_id="p2",
        app_instance_id="agent_system",
        status="queued",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        summary = build_regression_operator_summary(memory=memory, nightly_status=nightly_status)

    card = summary["refinement"]["governance"]["rollout_review_card"]
    assert card["title"] == "Review queue item q-primary"
    assert card["priority_tier"] == "primary"
    assert card["recommended_action"] == "stabilize_nightly_automation_control_plane"
    assert card["attention_reason"] == "consecutive_failures"


def test_trigger_manual_cycle_can_auto_apply_governance_selection(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem

    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)
    service._refinement_memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h1",
        proposal_id="regression-trigger-1",
        app_instance_id="agent_system",
        status="queued",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))
    service.run_cycle = Mock(return_value={"run_id": "manual-run-1"})

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        result = service.trigger_manual_cycle(client=Mock(), auto_apply_governance=True)

    assert result["triggered"] is True
    assert result["governance_rollout"]["applied"] is True
    assert result["governance_rollout"]["queue_id"] == "q-primary"
    assert result["governance_rollout"]["item"]["status"] == "applied"
    assert result["governance_rollout_summary"] == {
        "decision": "auto_applied",
        "action": "applied_selected_queue",
        "queue_id": "q-primary",
        "applied": True,
        "reason": None,
        "review_scope": "light_auto_apply_ok",
        "review_reason": "primary_selection_healthy",
        "decision_code": "tier.primary_auto_apply",
        "decision_label": "Primary tier auto-apply allowed",
        "render_badge": "AUTO | Primary tier auto-apply allowed",
        "render_operator_note": result["governance_rollout"]["preflight"]["render_operator_note"],
    }


def test_governance_execution_preflight_blocks_secondary_selection(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem

    service = build_service(tmp_path)
    service._refinement_memory.add_queue_item(RolloutQueueItem(
        queue_id="q-secondary",
        hypothesis_id="h1",
        proposal_id="regression-trigger-1",
        app_instance_id="agent_system",
        status="queued",
        note="regression_quality::execution_semantics::profile_performance_bottlenecks::execution::priority=secondary",
    ))
    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        preflight = service.build_governance_execution_preflight(nightly_status=None)
        result = service.apply_governance_selected_rollout(nightly_status=None)

    assert preflight["can_apply"] is False
    assert preflight["hold_reason"] == PREFLIGHT_HOLD_SECONDARY_REQUIRES_REVIEW
    assert result["applied"] is False
    assert result["preflight"]["hold_reason"] == PREFLIGHT_HOLD_SECONDARY_REQUIRES_REVIEW
    assert result["preflight"]["review_reason"] == PREFLIGHT_REVIEW_REASON_PRIORITY_SECONDARY
    assert result["preflight"]["matched_stage"] == "tier_gate"
    assert result["preflight"]["decision_code"] == "tier.secondary_requires_review"
    assert result["preflight"]["decision_label"] == "Secondary tier review required"


def test_trigger_manual_cycle_auto_apply_returns_preflight_metadata(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem

    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=3600)
    service._refinement_memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h1",
        proposal_id="regression-trigger-1",
        app_instance_id="agent_system",
        status="queued",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))
    service.run_cycle = Mock(return_value={"run_id": "manual-run-1"})
    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        result = service.trigger_manual_cycle(client=Mock(), auto_apply_governance=True)

    assert result["governance_rollout"]["applied"] is True
    assert result["governance_rollout"]["preflight"]["can_apply"] is True
    assert result["governance_rollout"]["preflight"]["required_review_scope"] == PREFLIGHT_REVIEW_SCOPE_LIGHT_AUTO_APPLY_OK
    assert result["governance_rollout"]["preflight"]["review_reason"] == PREFLIGHT_REVIEW_REASON_PRIMARY_SELECTION_HEALTHY
    assert result["governance_rollout"]["preflight"]["matched_stage"] == "tier_gate"
    assert result["governance_rollout"]["preflight"]["decision_code"] == "tier.primary_auto_apply"


def test_governance_execution_preflight_blocks_nonqueued_item(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem

    service = build_service(tmp_path)
    service._refinement_memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h1",
        proposal_id="regression-trigger-1",
        app_instance_id="agent_system",
        status="applied",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))
    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        preflight = service.build_governance_execution_preflight(nightly_status=None)

    assert preflight["can_apply"] is False
    assert preflight["hold_reason"] == "queue_status_blocked:applied"
    assert preflight["queue_status"] == "applied"
    assert preflight["review_scope"] == PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_QUEUE_STATE
    assert preflight["hold_category"] == "queue_status_blocked"
    assert preflight["matched_stage"] == "queue_state_gate"
    assert preflight["decision_code"] == "queue_state.status_blocked"
    assert preflight["decision_label"] == "Queue state blocked"


def test_governance_execution_preflight_exposes_priority_lane_metadata(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem

    service = build_service(tmp_path)
    service._refinement_memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h1",
        proposal_id="regression-trigger-1",
        app_instance_id="agent_system",
        status="queued",
        note="answer_shaping::misaligned_manual_override::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))
    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        preflight = service.build_governance_execution_preflight(nightly_status=None)

    assert preflight["priority_lane"] == "answer_shaping::tighten_evidence_boundary_guard"
    assert preflight["can_apply"] is True


def test_governance_execution_preflight_blocks_degraded_automation_health(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem

    service = build_service(tmp_path)
    service._refinement_memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h1",
        proposal_id="regression-trigger-1",
        app_instance_id="agent_system",
        status="queued",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))
    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "degraded",
            "attention_reason": "consecutive_failures",
            "last_tick_outcome": "failed",
            "consecutive_failures": 3,
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        preflight = service.build_governance_execution_preflight(nightly_status=nightly_status)

    assert preflight["can_apply"] is False
    assert preflight["hold_reason"] == PREFLIGHT_HOLD_AUTOMATION_DEGRADED_REQUIRES_REVIEW
    assert preflight["review_scope"] == PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_AUTOMATION
    assert preflight["review_reason"] == PREFLIGHT_REVIEW_REASON_AUTOMATION_DEGRADED
    assert preflight["matched_stage"] == "automation_health_gate"
    assert preflight["decision_code"] == "automation.degraded_requires_review"
    assert preflight["decision_label"] == "Automation degraded, review required"
    assert preflight["automation_health"] == "degraded"
    assert preflight["consecutive_failures"] == 3


def test_governance_execution_preflight_blocks_retry_pending_warning(tmp_path: Path) -> None:
    from unittest.mock import patch
    from app.models.refinement_loop import RolloutQueueItem

    service = build_service(tmp_path)
    service._refinement_memory.add_queue_item(RolloutQueueItem(
        queue_id="q-primary",
        hypothesis_id="h1",
        proposal_id="regression-trigger-1",
        app_instance_id="agent_system",
        status="queued",
        note="automation_control_plane::automation_recovery::stabilize_nightly_automation_control_plane::execution::priority=primary",
    ))
    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6500,
        "avg_fallback_count": 1.5,
        "avg_overreach_risk_count": 0.7,
        "answer_mode_totals": {"direct": 1, "verification_required": 2, "clarification_required": 1},
        "verification_mode_totals": {},
        "runs": [],
    }
    nightly_status = {
        "automation_control": {
            "automation_health": "warning",
            "attention_reason": "retry_pending",
            "last_tick_outcome": "skipped",
            "retry_pending": True,
        }
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 3}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]):
        preflight = service.build_governance_execution_preflight(nightly_status=nightly_status)

    assert preflight["can_apply"] is False
    assert preflight["hold_reason"] == PREFLIGHT_HOLD_AUTOMATION_RETRY_PENDING_REQUIRES_REVIEW
    assert preflight["review_scope"] == PREFLIGHT_REVIEW_SCOPE_OPERATOR_REVIEW_REQUIRED_DUE_TO_AUTOMATION
    assert preflight["review_reason"] == PREFLIGHT_REVIEW_REASON_AUTOMATION_RETRY_PENDING
    assert preflight["matched_stage"] == "automation_health_gate"
    assert preflight["decision_code"] == "automation.retry_pending_requires_review"
    assert preflight["decision_label"] == "Automation retry pending, review required"
    assert preflight["automation_health"] == "warning"



def test_chat_observation_digest_builds_from_live_chat_records(tmp_path) -> None:
    persist_chat_observation(probe={
        "topic": "api",
        "prompt": "帮我确认这个接口行为",
        "success": True,
        "latency_ms": 12,
        "response": "需要进一步验证后再判断",
        "answer_mode": "verification_required",
        "verification_mode": "required",
        "fallback_like": True,
        "overreach_risk": True,
        "source": "live_chat_request",
        "session_id": "session-live-1",
        "error_type": None,
    }, log_dir=tmp_path)

    digest = build_chat_observation_digest(session_id="session-live-1", log_dir=tmp_path)

    assert digest.total_observations == 1
    assert digest.failure_stage_counts["evidence"] == 1
    assert digest.observation_samples[0].run_id.startswith("live-chat-session-live-1")


def test_regression_dashboard_exposes_live_chat_observation_digest() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_governance_dashboard
    from app.models.governance_observation import GovernanceEvidenceDigest

    comparison = {
        "run_count": 1,
        "avg_latency_ms": 1000,
        "avg_fallback_count": 0,
        "avg_overreach_risk_count": 0,
        "answer_mode_totals": {"direct": 1},
        "verification_mode_totals": {"none": 1},
        "runs": [],
    }

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 1}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]),          patch("app.system.regression_dashboard.build_chat_observation_digest", return_value=GovernanceEvidenceDigest(total_observations=1, failure_stage_counts={"evidence": 1})):
        dashboard = build_regression_governance_dashboard(replay_session_id="session-live-2")

    assert dashboard["live_chat_observation_digest"]["total_observations"] == 1
    assert dashboard["live_chat_observation_digest"]["failure_stage_counts"]["evidence"] == 1




def test_regression_dashboard_merges_live_chat_observation_into_observation_digest() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_governance_dashboard
    from app.models.governance_observation import GovernanceEvidenceDigest

    comparison = {
        "run_count": 1,
        "avg_latency_ms": 1000,
        "avg_fallback_count": 0,
        "avg_overreach_risk_count": 0,
        "answer_mode_totals": {"direct": 1},
        "verification_mode_totals": {"none": 1},
        "runs": [{"summary": {"run_id": "run-merge-1"}}],
    }
    base_digest = GovernanceEvidenceDigest(total_observations=1, failure_stage_counts={"execution": 1})
    live_digest = GovernanceEvidenceDigest(total_observations=2, failure_stage_counts={"evidence": 2})

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value=comparison),          patch("app.system.regression_dashboard.build_topic_trends", return_value={"topics": {}, "run_count": 1}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]),          patch("app.system.regression_dashboard.read_run_details", return_value={"summary": {"run_id": "run-merge-1"}, "probes": []}),          patch("app.system.regression_dashboard.build_governance_evidence_digest", return_value=base_digest),          patch("app.system.regression_dashboard.build_chat_observation_digest", return_value=live_digest):
        dashboard = build_regression_governance_dashboard(replay_session_id="session-live-merge")

    assert dashboard["observation_digest"]["total_observations"] == 3
    assert dashboard["observation_digest"]["failure_stage_counts"]["execution"] == 1
    assert dashboard["observation_digest"]["failure_stage_counts"]["evidence"] == 2


def test_run_regression_governance_cycle_passes_session_id_into_trigger_application() -> None:
    from app.system.chat_regression import RegressionProbeResult, run_regression_governance_cycle

    captured = {}

    def fake_post(_path: str, payload: dict[str, object]) -> dict[str, object]:
        return {
            "success": True,
            "response": f"ok:{payload['message']}",
            "latency_ms": 5,
            "structured_answer": {"self_model": {"answer_mode": "direct", "verification_mode": "none"}},
        }

    def fake_apply(memory, **kwargs):
        captured.update(kwargs)
        return {"trigger_count": 0, "created_hypotheses": [], "created_verifications": [], "created_queue_items": []}

    result = run_regression_governance_cycle(
        fake_post,
        promote_evidence_fn=lambda **kwargs: {"promoted_count": 0, "promoted_evidence": [], "comparison": kwargs.get("comparison")},
        apply_triggers_fn=fake_apply,
        memory=object(),
        session_id="session-regression-nightly-service",
    )

    assert result["trigger_application"]["trigger_count"] == 0
    assert captured["replay_session_id"] == "session-regression-nightly-service"


def test_trigger_manual_cycle_uses_service_session_for_live_chat_governance(tmp_path: Path) -> None:
    from unittest.mock import Mock, patch
    from app.services.regression_nightly_control import RegressionNightlyControlService, REGRESSION_NIGHTLY_SERVICE_SESSION_ID

    service = build_service(tmp_path)
    service.register_nightly_schedule(interval_seconds=60)

    fake_cycle = {
        "run_id": "run-live-governance",
        "summary": {},
        "path": "/tmp/run-live-governance.jsonl",
        "evidence": {"promoted_count": 0},
        "trigger_application": {"trigger_count": 1},
    }

    with patch.object(service, "run_cycle", return_value=fake_cycle) as run_cycle_mock:
        result = service.trigger_manual_cycle(client=Mock())

    assert result["triggered"] is True
    assert run_cycle_mock.call_args.kwargs["session_id"] == REGRESSION_NIGHTLY_SERVICE_SESSION_ID

