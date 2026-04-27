from app.system.chat_regression import FIXED_PROMPT_MATRIX, make_testclient_poster, run_fixed_prompt_matrix, summarize_probe_payload


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
