from app.system.chat_regression import FIXED_PROMPT_MATRIX, summarize_probe_payload


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
