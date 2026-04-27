from pathlib import Path

from app.system.chat_regression import (
    FIXED_PROMPT_MATRIX,
    build_run_summary,
    build_multi_run_comparison,
    make_testclient_poster,
    persist_run_results,
    list_saved_runs,
    read_run_details,
    run_fixed_prompt_matrix,
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
