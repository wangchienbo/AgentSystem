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


def test_effective_user_id_isolated_by_run_id() -> None:
    assert harness._effective_user_id("user_system_01", None) == "user_system_01"
    assert harness._effective_user_id("user_system_01", "e2e-user-level-abc123") == "user_system_01__e2e-user-level-abc123"
