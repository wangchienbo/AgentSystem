from pathlib import Path

from app.refinement.refinement_memory import RefinementMemoryStore
from app.refinement.refinement_rollout import RefinementRolloutService
from app.system.regression_dashboard import apply_regression_triggers_to_refinement
from app.system.chat_regression import (
    FIXED_PROMPT_MATRIX,
    build_run_summary,
    build_multi_run_comparison,
    build_topic_trends,
    make_testclient_poster,
    persist_run_results,
    list_saved_runs,
    read_run_details,
    run_fixed_prompt_matrix,
    run_regression_governance_cycle,
    summarize_probe_payload,
)


def test_fixed_prompt_matrix_topics_are_stable() -> None:
    assert set(FIXED_PROMPT_MATRIX) == {"api", "validation", "telemetry", "storage"}
    assert all(FIXED_PROMPT_MATRIX.values())


def test_summarize_probe_payload_extracts_modes_and_risk() -> None:
    result = summarize_probe_payload(
        "telemetry",
        {
            "success": True,
            "response": "当前结论仍需进一步验证。已定位部分埋点。",
            "latency_ms": 123,
            "structured_answer": {
                "self_model": {
                    "answer_mode": "verification_required",
                    "verification_mode": "required",
                }
            },
        },
    )

    assert result.topic == "telemetry"
    assert result.latency_ms == 123
    assert result.answer_mode == "verification_required"
    assert result.verification_mode == "required"
    assert result.fallback_like is True
    assert result.overreach_risk is True


def test_summarize_probe_payload_defaults_for_missing_structure() -> None:
    result = summarize_probe_payload(
        "api",
        {
            "success": True,
            "response": "已完成接口梳理。",
            "latency_ms": 50,
        },
    )

    assert result.answer_mode == "direct"
    assert result.verification_mode == "none"
    assert result.fallback_like is False
    assert result.overreach_risk is False


def test_run_fixed_prompt_matrix_executes_all_topics() -> None:
    calls: list[tuple[str, dict]] = []

    def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {
            "success": True,
            "response": f"已处理 {payload['message']}",
            "latency_ms": 42,
            "structured_answer": {
                "self_model": {
                    "answer_mode": "direct",
                    "verification_mode": "none",
                }
            },
        }

    results = run_fixed_prompt_matrix(fake_post)

    assert len(results) == 4
    assert [r.topic for r in results] == ["api", "validation", "telemetry", "storage"]
    assert all(path == "/api/chat" for path, _ in calls)
    assert [payload["message"] for _, payload in calls] == list(FIXED_PROMPT_MATRIX.values())


def test_make_testclient_poster_wraps_client_json_response() -> None:
    class FakeResponse:
        def json(self) -> dict:
            return {"success": True, "response": "ok", "latency_ms": 1}

    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        def post(self, path: str, json: dict):
            self.calls.append((path, json))
            return FakeResponse()

    client = FakeClient()
    post_json = make_testclient_poster(client)
    payload = post_json("/api/chat", {"message": "hello"})

    assert payload["success"] is True
    assert client.calls == [("/api/chat", {"message": "hello"})]


def test_build_run_summary_aggregates_modes_and_latency() -> None:
    results = [
        summarize_probe_payload("api", {"success": True, "response": "已完成接口梳理。", "latency_ms": 100}),
        summarize_probe_payload("telemetry", {"success": True, "response": "当前结论仍需进一步验证。", "latency_ms": 300, "structured_answer": {"self_model": {"answer_mode": "verification_required", "verification_mode": "required"}}}),
    ]

    summary = build_run_summary(results, run_id="run-1", started_at="2026-04-27T00:00:00Z")

    assert summary.run_id == "run-1"
    assert summary.topic_count == 2
    assert summary.success_count == 2
    assert summary.avg_latency_ms == 200
    assert summary.fallback_count == 1
    assert summary.overreach_risk_count == 1
    assert summary.answer_mode_counts["direct"] == 1
    assert summary.answer_mode_counts["verification_required"] == 1


def test_persist_run_results_writes_summary_and_probes(tmp_path: Path) -> None:
    results = [
        summarize_probe_payload("api", {"success": True, "response": "已完成接口梳理。", "latency_ms": 100}),
        summarize_probe_payload("storage", {"success": True, "response": "建议做轻量验证。", "latency_ms": 200, "structured_answer": {"self_model": {"answer_mode": "tool_required", "verification_mode": "light"}}}),
    ]
    summary = build_run_summary(results, run_id="run-persist", started_at="2026-04-27T00:00:00Z")

    path = persist_run_results(results, summary, log_dir=tmp_path)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert '"kind": "summary"' in lines[0]
    assert '"kind": "probe"' in lines[1]
    assert '"run_id": "run-persist"' in lines[1]


def test_list_saved_runs_and_read_run_details(tmp_path: Path) -> None:
    results = [summarize_probe_payload("api", {"success": True, "response": "ok", "latency_ms": 10})]
    summary = build_run_summary(results, run_id="run-read", started_at="2026-04-27T00:00:00Z")
    persist_run_results(results, summary, log_dir=tmp_path)

    rows = list_saved_runs(log_dir=tmp_path, limit=5)
    assert len(rows) == 1
    assert rows[0]["summary"]["run_id"] == "run-read"

    detail = read_run_details("run-read", log_dir=tmp_path)
    assert detail is not None
    assert detail["summary"]["run_id"] == "run-read"
    assert detail["probes"][0]["topic"] == "api"


def test_build_multi_run_comparison_aggregates_saved_summaries(tmp_path: Path) -> None:
    r1 = [summarize_probe_payload("api", {"success": True, "response": "ok", "latency_ms": 100})]
    s1 = build_run_summary(r1, run_id="run-a", started_at="2026-04-27T00:00:00Z")
    persist_run_results(r1, s1, log_dir=tmp_path)

    r2 = [summarize_probe_payload("telemetry", {"success": True, "response": "当前结论仍需进一步验证。", "latency_ms": 300, "structured_answer": {"self_model": {"answer_mode": "verification_required", "verification_mode": "required"}}})]
    s2 = build_run_summary(r2, run_id="run-b", started_at="2026-04-27T00:10:00Z")
    persist_run_results(r2, s2, log_dir=tmp_path)

    comp = build_multi_run_comparison(log_dir=tmp_path, limit=5)

    assert comp["run_count"] == 2
    assert comp["avg_latency_ms"] == 200
    assert comp["avg_fallback_count"] == 0.5
    assert comp["avg_overreach_risk_count"] == 0.5
    assert comp["answer_mode_totals"]["direct"] == 1
    assert comp["answer_mode_totals"]["verification_required"] == 1


def test_build_regression_evidence_from_comparison_generates_correct_signals() -> None:
    from app.system.regression_evidence_bridge import build_regression_evidence_from_comparison

    comparison = {
        "run_count": 3,
        "avg_latency_ms": 6000,
        "avg_fallback_count": 2.0,
        "avg_overreach_risk_count": 1.5,
        "answer_mode_totals": {"verification_required": 4, "clarification_required": 3, "direct": 3},
        "verification_mode_totals": {"none": 5, "required": 5},
        "runs": [],
    }

    evidence_list = build_regression_evidence_from_comparison(comparison)
    assert len(evidence_list) >= 3

    topics = [e.summary for e in evidence_list]
    assert any("latency" in s for s in topics)
    assert any("fallback" in s for s in topics)
    assert any("overreach" in s for s in topics)

    for e in evidence_list:
        assert e.category in {"workflow_failure", "policy_pressure", "clarify_unresolved"}
        assert e.app_instance_id == "chat_regression"
        assert e.impact_area in {"runtime", "response_quality", "boundary_policy"}


def test_build_regression_evidence_from_comparison_no_evidence_for_small_data() -> None:
    from app.system.regression_evidence_bridge import build_regression_evidence_from_comparison

    comparison = {
        "run_count": 1,
        "avg_latency_ms": 1000,
        "avg_fallback_count": 0,
        "avg_overreach_risk_count": 0,
        "answer_mode_totals": {"direct": 2},
        "verification_mode_totals": {"none": 2},
        "runs": [],
    }

    evidence_list = build_regression_evidence_from_comparison(comparison)
    assert evidence_list == []


def test_build_topic_trends_groups_probes_by_topic(tmp_path: Path) -> None:
    r1 = [
        summarize_probe_payload("api", {"success": True, "response": "ok", "latency_ms": 100}),
        summarize_probe_payload("storage", {"success": True, "response": "ok", "latency_ms": 50}),
    ]
    s1 = build_run_summary(r1, run_id="run-a", started_at="2026-04-27T00:00:00Z")
    persist_run_results(r1, s1, log_dir=tmp_path)

    r2 = [
        summarize_probe_payload("api", {"success": True, "response": "ok", "latency_ms": 200}),
        summarize_probe_payload("storage", {"success": True, "response": "过度", "latency_ms": 60,
            "structured_answer": {"self_model": {"answer_mode": "verification_required", "verification_mode": "required"}}}),
    ]
    s2 = build_run_summary(r2, run_id="run-b", started_at="2026-04-27T00:10:00Z")
    persist_run_results(r2, s2, log_dir=tmp_path)

    trends = build_topic_trends(log_dir=tmp_path, limit=5)

    assert trends["run_count"] == 2
    assert set(trends["topics"].keys()) == {"api", "storage"}

    api_trend = trends["topics"]["api"]
    assert api_trend["run_count"] == 2
    assert api_trend["avg_latency_ms"] == 150
    assert api_trend["avg_fallback"] == 0.0

    storage_trend = trends["topics"]["storage"]
    assert storage_trend["run_count"] == 2
    assert storage_trend["avg_overreach"] == 0.5
    assert storage_trend["answer_mode_counts"]["direct"] == 1
    assert storage_trend["answer_mode_counts"]["verification_required"] == 1


def test_build_topic_trends_empty_on_no_runs(tmp_path: Path) -> None:
    trends = build_topic_trends(log_dir=tmp_path, limit=5)
    assert trends["run_count"] == 0
    assert trends["topics"] == {}


def test_apply_regression_triggers_to_refinement_persists_records() -> None:
    memory = RefinementMemoryStore()

    from unittest.mock import patch

    fake_triggers = {
        "triggers": [
            {
                "trigger_id": "regression-trigger-1",
                "signal": "elevated_latency",
                "level": "warning",
                "recommended_action": "profile_performance_bottlenecks",
                "detail": "Average latency 6200ms across 3 runs",
                "generated_at": "2026-04-27T00:00:00Z",
            }
        ],
        "trigger_count": 1,
        "dashboard_comparison": {"run_count": 3},
        "generated_at": "2026-04-27T00:00:00Z",
    }

    with patch("app.system.regression_dashboard.build_regression_triggers", return_value=fake_triggers):
        result = apply_regression_triggers_to_refinement(memory)

    assert result["trigger_count"] == 1
    assert len(memory.list_hypotheses("agent_system")) == 1
    assert len(memory.list_verifications()) == 1
    assert len(memory.list_queue("agent_system")) == 1


def test_refinement_rollout_allows_regression_queue_apply() -> None:
    from app.models.refinement_loop import RolloutQueueItem

    class FakeProposalReview:
        def review(self, request):
            raise AssertionError("proposal review should not be called for regression queue items")

    memory = RefinementMemoryStore()
    memory.add_queue_item(
        RolloutQueueItem(
            queue_id="reg-queue-1",
            hypothesis_id="reg-hyp-1",
            proposal_id="regression-trigger-1",
            app_instance_id="agent_system",
            status="queued",
            note="profile_performance_bottlenecks",
        )
    )
    rollout = RefinementRolloutService(memory=memory, proposal_review=FakeProposalReview())

    item = rollout.transition("reg-queue-1", "apply")

    assert item.status == "applied"
    assert "regression" in item.note


def test_build_regression_operator_summary_reflects_live_queue_stats() -> None:
    from unittest.mock import patch
    from app.system.regression_dashboard import build_regression_operator_summary

    memory = RefinementMemoryStore()
    fake_triggers = {
        "triggers": [
            {
                "trigger_id": "regression-trigger-1",
                "signal": "elevated_latency",
                "level": "warning",
                "recommended_action": "profile_performance_bottlenecks",
                "detail": "Average latency 6200ms across 3 runs",
                "generated_at": "2026-04-27T00:00:00Z",
            }
        ],
        "trigger_count": 1,
        "dashboard_comparison": {"run_count": 3},
        "generated_at": "2026-04-27T00:00:00Z",
    }

    with patch("app.system.regression_dashboard.build_regression_triggers", return_value=fake_triggers):
        apply_regression_triggers_to_refinement(memory)

    queue_id = memory.list_queue("agent_system")[0].queue_id
    rollout = RefinementRolloutService(memory=memory, proposal_review=type("P", (), {"review": lambda self, req: None})())
    rollout.transition(queue_id, "apply")

    with patch("app.system.regression_dashboard.build_multi_run_comparison", return_value={"run_count": 1, "avg_latency_ms": 6000, "avg_fallback_count": 0, "avg_overreach_risk_count": 0, "answer_mode_totals": {"direct": 1}}),          patch("app.system.regression_dashboard.build_topic_trends", return_value={}),          patch("app.system.regression_dashboard.list_regression_evidence_history", return_value=[]),          patch("app.system.regression_dashboard.build_regression_triggers", return_value=fake_triggers):
        summary = build_regression_operator_summary(memory=memory)

    stats = summary["refinement"]["governance"]["stats"]
    assert stats["applied_items"] == 1
    assert summary["refinement"]["governance"]["recent_queue"]["items"][0]["status"] == "applied"


def test_run_regression_governance_cycle_returns_full_bundle() -> None:
    memory = RefinementMemoryStore()

    def fake_post(path: str, payload: dict) -> dict:
        return {
            "success": True,
            "response": "已完成接口梳理。",
            "latency_ms": 50,
            "structured_answer": {"self_model": {"answer_mode": "direct", "verification_mode": "none"}},
        }

    def fake_promote(**kwargs):
        return {"promoted_count": 1, "promoted_evidence": [{"evidence_id": "ev-1"}], "comparison": {"run_count": 2}}

    def fake_apply(mem):
        assert mem is memory
        return {"trigger_count": 1, "created_hypotheses": [{"hypothesis_id": "reg-hyp-1"}], "created_verifications": [], "created_queue_items": []}

    result = run_regression_governance_cycle(
        fake_post,
        persist_results_fn=lambda results, summary: Path("/tmp/") / f"{summary.run_id}.jsonl",
        promote_evidence_fn=fake_promote,
        apply_triggers_fn=fake_apply,
        memory=memory,
    )

    assert result["summary"]["topic_count"] == 4
    assert result["evidence"]["promoted_count"] == 1
    assert result["trigger_application"]["trigger_count"] == 1
