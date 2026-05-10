from __future__ import annotations

import tests.e2e.test_50_scenarios_20_turns_user_level as harness


class _AlwaysTimeoutClient:
    def send_message(self, user_id: str, message: str, session_id: str | None = None, payload=None):
        raise harness.httpx.TimeoutException("boom")

    def get_history(self, session_id: str):
        return []


class _AlwaysOkClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def send_message(self, user_id: str, message: str, session_id: str | None = None, payload=None):
        self.calls.append(message)
        return {"ok": True, "session_id": "session_ok", "response": f"echo:{message}", "content": f"echo:{message}"}

    def get_history(self, session_id: str):
        return [
            {"role": "user", "content": msg} for msg in self.calls
        ] + [
            {"role": "assistant", "content": f"echo:{msg}"} for msg in self.calls
        ]


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


def test_run_scenario_respects_max_turns_limit() -> None:
    scenario = {
        "id": "SYY",
        "name": "bounded scenario",
        "user_id": "user_ok",
        "turns": ["one", "two", "three", "four"],
    }

    client = _AlwaysOkClient()
    result = harness.run_scenario(
        client,
        scenario,
        delay=0,
        max_turns=2,
    )

    assert client.calls == ["one", "two"]
    assert len(result.turns) == 2
    assert result.total_ok == 2
    assert result.total_turns == 4
