from pathlib import Path

from app.system.chat_regression import (
    FIXED_PROMPT_MATRIX,
    build_run_summary,
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
