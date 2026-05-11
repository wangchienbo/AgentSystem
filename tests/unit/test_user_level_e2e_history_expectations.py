from __future__ import annotations

import tests.e2e.test_50_scenarios_20_turns_user_level as harness


def test_history_expectations_follow_executed_turn_count_for_bounded_runs() -> None:
    scenario = {"id": "SZZ", "name": "bounded", "user_id": "user_z"}
    result = harness.ScenarioResult(
        scenario_id="SZZ",
        name="bounded",
        user_id="user_z",
        total_turns=20,
        turns=[
            harness.TurnResult(turn_index=1, message="one", ok=True),
            harness.TurnResult(turn_index=2, message="two", ok=True),
        ],
    )
    history = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "ok1"},
        {"role": "user", "content": "two"},
        {"role": "assistant", "content": "ok2"},
    ]

    expectation = harness._evaluate_scenario_history(scenario, history, result)

    assert expectation.ok is True
    assert any("user turn count matched: 2" in item for item in expectation.checks)
