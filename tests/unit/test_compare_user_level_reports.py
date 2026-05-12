from __future__ import annotations

from tests.e2e.compare_user_level_reports import compare_reports


def test_compare_reports_detects_improvement_and_regression() -> None:
    before = {
        "run_id": "before-run",
        "scenarios_all_ok": 1,
        "total_ok": 3,
        "total_fail": 1,
        "total_errors": 0,
        "pass_rate_pct": 75.0,
        "details": [
            {"id": "S01", "verdict": "failed", "ok": 1, "fail": 1, "errors": 0, "history_expectation_ok": False},
            {"id": "S02", "verdict": "passed", "ok": 2, "fail": 0, "errors": 0, "history_expectation_ok": True},
        ],
    }
    after = {
        "run_id": "after-run",
        "scenarios_all_ok": 1,
        "total_ok": 2,
        "total_fail": 2,
        "total_errors": 0,
        "pass_rate_pct": 50.0,
        "details": [
            {"id": "S01", "verdict": "passed", "ok": 2, "fail": 0, "errors": 0, "history_expectation_ok": True},
            {"id": "S02", "verdict": "failed", "ok": 0, "fail": 2, "errors": 0, "history_expectation_ok": False},
        ],
    }

    comparison = compare_reports(before, after)

    assert comparison["before_report_label"] == "before-run"
    assert comparison["after_report_label"] == "after-run"
    assert comparison["pass_rate_delta_pct"] == -25.0
    assert comparison["improved_scenarios"] == ["S01"]
    assert comparison["regressed_scenarios"] == ["S02"]
    assert comparison["comparison_status"] == "regression_detected"


def test_compare_reports_handles_added_removed_and_unchanged_scenarios() -> None:
    before = {
        "scenarios_all_ok": 1,
        "total_ok": 1,
        "total_fail": 0,
        "total_errors": 0,
        "pass_rate_pct": 100.0,
        "details": [
            {"id": "S01", "verdict": "passed", "ok": 1, "fail": 0, "errors": 0, "history_expectation_ok": True},
            {"id": "S02", "verdict": "passed", "ok": 1, "fail": 0, "errors": 0, "history_expectation_ok": True},
        ],
    }
    after = {
        "scenarios_all_ok": 2,
        "total_ok": 2,
        "total_fail": 0,
        "total_errors": 0,
        "pass_rate_pct": 100.0,
        "details": [
            {"id": "S02", "verdict": "passed", "ok": 1, "fail": 0, "errors": 0, "history_expectation_ok": True},
            {"id": "S03", "verdict": "passed", "ok": 1, "fail": 0, "errors": 0, "history_expectation_ok": True},
        ],
    }

    comparison = compare_reports(before, after)

    assert comparison["comparison_status"] == "ok"
    assert comparison["added_scenarios"] == ["S03"]
    assert comparison["removed_scenarios"] == ["S01"]
    assert comparison["unchanged_scenarios"] == ["S02"]
