from __future__ import annotations

import tests.e2e.test_50_scenarios_20_turns_user_level as harness


class _AlwaysTimeoutClient:
    def send_message(self, user_id: str, message: str, session_id: str | None = None, payload=None):
        raise harness.httpx.TimeoutException("boom")

    def get_history(self, session_id: str):
        return []


def test_run_scenario_aborts_after_max_consecutive_failures() -> None:
    scenario = {
        "id": "SXX",
        "name": "timeout scenario",
        "user_id": "user_timeout",
        "turns": ["one", "two", "three", "four"],
    }

    result = harness.run_scenario(
        _AlwaysTimeoutClient(),
        scenario,
        delay=0,
        turn_timeout=1.0,
        max_consecutive_failures=2,
    )

    assert result.aborted_early is True
    assert result.abort_reason == "consecutive_failures=2"
    assert len(result.turns) == 2
    assert result.total_fail == 2
    assert result.total_error == 2
