from __future__ import annotations

from tests.e2e.merge_user_level_reports import merge_reports


def test_merge_reports_combines_split_bounded_artifacts() -> None:
    first = {
        "run_id": "first-25",
        "base_url": "http://127.0.0.1:80",
        "delay_seconds": 0,
        "timeout_seconds": 120,
        "max_turns_per_scenario": 5,
        "max_consecutive_failures": 0,
        "total_scenarios": 25,
        "planned_total_turns": 500,
        "executed_turn_budget": 125,
        "scenarios_all_ok": 25,
        "scenarios_with_fail": 0,
        "total_turns": 125,
        "total_ok": 125,
        "total_fail": 0,
        "total_errors": 0,
        "total_seconds": 78,
        "details": [{"id": "S01", "verdict": "pass"}, {"id": "S25", "verdict": "pass"}],
    }
    second = {
        "run_id": "last-25",
        "base_url": "http://127.0.0.1:80",
        "delay_seconds": 0,
        "timeout_seconds": 120,
        "max_turns_per_scenario": 5,
        "max_consecutive_failures": 0,
        "total_scenarios": 25,
        "planned_total_turns": 500,
        "executed_turn_budget": 125,
        "scenarios_all_ok": 25,
        "scenarios_with_fail": 0,
        "total_turns": 125,
        "total_ok": 125,
        "total_fail": 0,
        "total_errors": 0,
        "total_seconds": 70,
        "details": [{"id": "S26", "verdict": "pass"}, {"id": "S50", "verdict": "pass"}],
    }

    merged = merge_reports([first, second])

    assert merged["merge_kind"] == "bounded_split_after_artifact"
    assert merged["source_report_count"] == 2
    assert merged["source_report_labels"] == ["first-25", "last-25"]
    assert merged["total_scenarios"] == 50
    assert merged["planned_total_turns"] == 1000
    assert merged["executed_turn_budget"] == 250
    assert merged["scenarios_all_ok"] == 50
    assert merged["total_turns"] == 250
    assert merged["total_ok"] == 250
    assert merged["total_seconds"] == 148
    assert merged["pass_rate_pct"] == 100.0
    assert merged["avg_turn_seconds"] == 0.6
    assert [item["id"] for item in merged["details"]] == ["S01", "S25", "S26", "S50"]
