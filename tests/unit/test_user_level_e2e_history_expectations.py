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


def test_history_expectations_ignore_s31_synthetic_empty_inputs() -> None:
    scenario = {"id": "S31", "name": "invalid-input", "user_id": "user_err"}
    result = harness.ScenarioResult(
        scenario_id="S31",
        name="invalid-input",
        user_id="user_err",
        total_turns=20,
        turns=[
            harness.TurnResult(turn_index=1, message="帮我创建一个App", ok=True, session_id="session_err", content_preview="drafted"),
            harness.TurnResult(turn_index=2, message="", ok=True, content_preview="(empty input — expected to handle gracefully)"),
            harness.TurnResult(turn_index=3, message="   ", ok=True, content_preview="(empty input — expected to handle gracefully)"),
            harness.TurnResult(turn_index=4, message="创建一个名字叫空的App", ok=True, session_id="session_err", content_preview="ready"),
            harness.TurnResult(turn_index=5, message="创建一个特殊字符的App: @#$%", ok=True, session_id="session_err", content_preview="running"),
        ],
    )
    history = [
        {"role": "user", "content": "帮我创建一个App"},
        {"role": "assistant", "content": "drafted"},
        {"role": "user", "content": "创建一个名字叫空的App"},
        {"role": "assistant", "content": "ready"},
        {"role": "user", "content": "创建一个特殊字符的App: @#$%"},
        {"role": "assistant", "content": "running"},
    ]

    expectation = harness._evaluate_scenario_history(scenario, history, result)

    assert expectation.ok is True
    assert any("user turn count matched: 3" in item for item in expectation.checks)




def test_effective_user_id_isolated_by_run_id() -> None:
    assert harness._effective_user_id("user_system_01", None) == "user_system_01"
    assert harness._effective_user_id("user_system_01", "e2e-user-level-abc123") == "user_system_01__e2e-user-level-abc123"
