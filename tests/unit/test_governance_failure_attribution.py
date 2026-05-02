from __future__ import annotations

from app.system.governance_failure_attribution import classify_governance_failure


def test_classify_governance_failure_requirement_misunderstanding() -> None:
    result = classify_governance_failure({
        "answer_mode": "clarification_required",
        "response": "请先澄清你的目标",
    })

    assert result.failure_stage == "requirement_understanding"
    assert result.signal == "requirement_misunderstanding"


def test_classify_governance_failure_routing_error() -> None:
    result = classify_governance_failure({
        "routing_error": True,
        "route_selected": "api.inspect",
    })

    assert result.failure_stage == "routing"
    assert result.signal == "routing_error"


def test_classify_governance_failure_missing_evidence() -> None:
    result = classify_governance_failure({
        "verification_mode": "evidence_required",
        "response": "需要进一步验证",
    })

    assert result.failure_stage == "evidence"
    assert result.signal == "missing_evidence"


def test_classify_governance_failure_bad_tool_execution() -> None:
    result = classify_governance_failure({
        "tool_error": True,
        "tool_name": "read_file",
    })

    assert result.failure_stage == "execution"
    assert result.signal == "bad_tool_execution"


def test_classify_governance_failure_weak_final_answer_shaping() -> None:
    result = classify_governance_failure({
        "overreach_risk": True,
        "response": "这里还不能直接下结论",
    })

    assert result.failure_stage == "answer_shaping"
    assert result.signal == "weak_final_answer_shaping"


def test_classify_governance_failure_respects_explicit_stage() -> None:
    result = classify_governance_failure({
        "failure_stage": "execution",
        "routing_error": True,
    })

    assert result.failure_stage == "execution"
    assert result.signal == "bad_tool_execution"


def test_classify_governance_failure_healthy_default() -> None:
    result = classify_governance_failure({
        "success": True,
        "answer_mode": "direct",
        "verification_mode": "none",
    })

    assert result.failure_stage is None
    assert result.signal == "healthy_observation"
